Before you enable the gdrivesync plugin follow these guidelines.

# Authentication
Drive API requires OAuth2.0 for authentication. PyDrive2 makes your life much easier by handling complex authentication steps for you.

Go to [APIs Console](https://console.developers.google.com/iam-admin/projects) and make your own project.

Search for ‘Google Drive API’, select the entry, and click ‘Enable’.

Select ‘Credentials’ from the left menu, click ‘Create Credentials’, select ‘OAuth client ID’.

Now, the product name and consent screen need to be set -> click ‘Configure consent screen’ and follow the instructions. Once finished:

Select ‘Application type’ to be Desktop application.

Enter an appropriate name.

Input http://localhost/ for ‘Authorized redirect URIs’.

Select the correct oauth scope:

    - drive
    - drive.install

Click ‘Create’.

Click ‘Download JSON’ and copy the contents to /root/client_secrets.json.

Then copy your client_id and client_secret to /root/settings.yaml

# Login to google

When you have done this please run the following command in your ssh shell:

`sudo pwnagotchi google login`

And follow the steps, after which you can enable the plugin and let the magic begin.

# Functionality
Set a backup folder in config file

It will then upload a zip file there of all your backup files.

If you have a new device you only need to log in with Google and enable the plugin, it will then download the previously made backup and reboot.
