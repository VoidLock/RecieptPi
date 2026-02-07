"""Auto-update checker for receipt printer application.

Checks GitHub for new releases and performs git-based updates.
"""

import logging
import subprocess
import time
import threading
import requests
from pathlib import Path

from . import config


class UpdateChecker(threading.Thread):
    """Background thread that checks for updates and optionally auto-updates.
    
    Periodically checks GitHub releases API for new versions. If AUTO_UPDATE is enabled
    and running in server mode, will automatically git pull and restart the service.
    
    Args:
        interval (int): Check interval in seconds (default from config.UPDATE_CHECK_INTERVAL)
        server_mode (bool): If True, running as systemd service (can auto-restart)
        error_notifier (str): Optional ntfy URL for error notifications
    """
    
    def __init__(self, interval=None, server_mode=False, error_notifier=None):
        super().__init__(daemon=True, name="UpdateChecker")
        self.interval = interval or config.UPDATE_CHECK_INTERVAL
        self.server_mode = server_mode
        self.error_notifier = error_notifier
        self._stop_event = threading.Event()
        self.current_version = self._get_current_version()
        
    def run(self):
        """Main update checking loop."""
        if not config.AUTO_UPDATE:
            logging.info("Auto-update disabled (AUTO_UPDATE=false)")
            return
            
        logging.info(f"Update checker started (interval: {self.interval}s, repo: {config.GITHUB_REPO})")
        logging.info(f"Current version: {self.current_version or 'unknown'}")
        
        # Wait a bit before first check to let app fully start
        time.sleep(60)
        
        while not self._stop_event.is_set() and not config.STOP_EVENT.is_set():
            try:
                self._check_for_updates()
            except Exception as e:
                logging.error(f"Update check failed: {e}")
                if self.error_notifier:
                    self._send_error("Update Check Failed", str(e))
            
            # Sleep in small intervals so we can exit quickly if needed
            for _ in range(self.interval):
                if self._stop_event.is_set() or config.STOP_EVENT.is_set():
                    break
                time.sleep(1)
    
    def stop(self):
        """Stop the update checker."""
        self._stop_event.set()
    
    def _get_current_version(self):
        """Get current git version (tag or commit hash).
        
        Returns:
            str: Version string or None if not in git repo
        """
        try:
            # Try to get latest tag
            result = subprocess.run(
                ["git", "describe", "--tags", "--abbrev=0"],
                capture_output=True,
                text=True,
                timeout=5,
                cwd=self._get_repo_path()
            )
            if result.returncode == 0:
                return result.stdout.strip()
            
            # Fallback to commit hash
            result = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                capture_output=True,
                text=True,
                timeout=5,
                cwd=self._get_repo_path()
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception as e:
            logging.debug(f"Could not get current version: {e}")
        
        return None
    
    def _get_repo_path(self):
        """Get the repository root path.
        
        Returns:
            Path: Repository root directory
        """
        return Path(__file__).parent.parent
    
    def _check_for_updates(self):
        """Check GitHub for new releases."""
        logging.debug(f"Checking for updates from {config.GITHUB_REPO}...")
        
        # Try latest release first
        api_url = f"https://api.github.com/repos/{config.GITHUB_REPO}/releases/latest"
        
        try:
            response = requests.get(api_url, timeout=10)
            
            if response.status_code == 404:
                # No releases yet, check tags instead
                logging.debug("No releases found, checking tags...")
                self._check_tags_for_updates()
                return
            
            response.raise_for_status()
            latest_release = response.json()
            latest_version = latest_release.get("tag_name", "").lstrip("v")
            
            if not latest_version:
                logging.warning("No release tag found on GitHub")
                return
            
            current_version = (self.current_version or "").lstrip("v")
            
            if latest_version != current_version:
                logging.info(f"New version available: {latest_version} (current: {current_version})")
                
                if config.AUTO_UPDATE:
                    self._perform_update(latest_version)
                else:
                    logging.info("Auto-update disabled - skipping update")
            else:
                logging.debug(f"Already on latest version: {latest_version}")
                
        except requests.RequestException as e:
            logging.warning(f"Failed to check GitHub releases: {e}")
    
    def _check_tags_for_updates(self):
        """Check GitHub tags as fallback when no releases exist."""
        api_url = f"https://api.github.com/repos/{config.GITHUB_REPO}/tags"
        
        try:
            response = requests.get(api_url, timeout=10)
            response.raise_for_status()
            tags = response.json()
            
            if not tags:
                logging.debug("No tags found on GitHub")
                return
            
            # Get the latest tag
            latest_tag = tags[0].get("name", "").lstrip("v")
            current_version = (self.current_version or "").lstrip("v")
            
            if latest_tag and latest_tag != current_version:
                logging.info(f"New tag available: {latest_tag} (current: {current_version})")
                
                if config.AUTO_UPDATE:
                    self._perform_update(latest_tag)
            else:
                logging.debug(f"Already on latest tag: {latest_tag}")
                
        except requests.RequestException as e:
            logging.debug(f"Failed to check GitHub tags: {e}")
    
    def _perform_update(self, new_version):
        """Perform git pull and restart service.
        
        Args:
            new_version (str): Version being updated to
        """
        logging.info(f"Starting update to version {new_version}...")
        
        try:
            repo_path = self._get_repo_path()
            
            # Ensure we're on a clean state
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                capture_output=True,
                text=True,
                timeout=5,
                cwd=repo_path
            )
            
            if result.stdout.strip():
                logging.warning("Working directory has uncommitted changes - skipping update")
                self._send_error("Update Skipped", "Working directory has uncommitted changes")
                return
            
            # Pull latest changes
            logging.info("Running git pull...")
            result = subprocess.run(
                ["git", "pull", "origin", "main"],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=repo_path
            )
            
            if result.returncode != 0:
                error_msg = f"Git pull failed: {result.stderr}"
                logging.error(error_msg)
                self._send_error("Update Failed", error_msg)
                return
            
            logging.info(f"Successfully updated to {new_version}")
            logging.info("Git pull output: " + result.stdout.strip())
            
            # Restart service if in server mode
            if self.server_mode:
                self._restart_service()
            else:
                logging.info("Not in server mode - manual restart required")
                print(f"\n{'='*60}")
                print(f"🔄 Updated to version {new_version}")
                print(f"   Please restart the application to apply changes")
                print(f"{'='*60}\n")
                
        except Exception as e:
            error_msg = f"Update failed: {str(e)}"
            logging.error(error_msg, exc_info=True)
            self._send_error("Update Failed", error_msg)
    
    def _restart_service(self):
        """Restart the systemd service."""
        logging.info("Restarting systemd service...")
        
        try:
            # Trigger service restart by exiting with special code
            # The systemd service should have Restart=always configured
            logging.info("Triggering service restart...")
            config.STOP_EVENT.set()
            
            # Alternative: directly call systemctl (requires sudo privileges)
            # subprocess.run(["systemctl", "restart", "receipt-printer"], timeout=5)
            
        except Exception as e:
            logging.error(f"Failed to restart service: {e}")
            self._send_error("Restart Failed", str(e))
    
    def _send_error(self, title, message):
        """Send error notification to ntfy topic using native format."""
        if not self.error_notifier:
            return
        try:
            import socket
            hostname = socket.gethostname()
            # Use ntfy native format: POST with title and tags as headers
            headers = {
                "Title": f"Application Error on {hostname}",
                "Tags": "rotating_light,error",
                "Priority": "high"
            }
            requests.post(self.error_notifier, data=message, headers=headers, timeout=5)
        except Exception as e:
            logging.error(f"Failed to send error notification: {e}")
