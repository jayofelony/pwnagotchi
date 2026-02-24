Before you enable the gdrivesync plugin, follow these guidelines.

---

# Authentication

The Google Drive API requires OAuth 2.0 for authentication. PyDrive2 makes this much easier by handling the complex authentication steps for you.

1. Go to the [APIs Console](https://console.developers.google.com/iam-admin/projects) and create a new project.

2. Search for **Google Drive API**, select the entry, and click **Enable**.

3. Select **Credentials** from the left menu.

4. Click **Create Credentials** and select **OAuth client ID**.

5. You must now configure the consent screen:

   * Click **Configure consent screen**.
   * Follow the instructions to complete the setup.

6. Once finished:

   * Select **Application type** and choose **Desktop application**.
   * Enter an appropriate name.
   * Enter `http://localhost/` for **Authorized redirect URIs**.
   * Select the correct OAuth scopes:

     * `drive`
     * `drive.install`

7. Click **Create**.

8. Click **Download JSON** and copy the contents to:

   ```
   /root/client_secrets.json
   ```

9. Copy your `client_id` and `client_secret` into:

   ```
   /root/settings.yaml
   ```

---

# Login to Google

After completing the steps above, run the following command in your SSH shell:

```
sudo pwnagotchi google login
```

Follow the on-screen instructions. Once completed, you can enable the plugin and let the magic begin.

---

# Functionality

1. Set a backup folder in the config file.

2. The plugin will upload a ZIP file containing all your backup files to that folder.

3. If you set up a new device, simply log in with Google and enable the plugin. It will automatically download the previously created backup and reboot the device.

---

If you would like, I can also format this in proper GitHub-flavored Markdown with badges, notes, and troubleshooting sections.
