# Setting Up FreeSWITCH with Twilio SIP Trunking on AWS

This comprehensive guide will walk you through setting up FreeSWITCH on an AWS EC2 Debian instance and integrating it with Twilio for outbound calling capabilities.

## Table of Contents

1. [AWS EC2 Setup](#aws-ec2-setup)
2. [FreeSWITCH Installation](#freeswitch-installation)
3. [FreeSWITCH Configuration](#freeswitch-configuration)
4. [Twilio SIP Trunk Setup](#twilio-sip-trunk-setup)
5. [Integration Testing](#integration-testing)

## AWS EC2 Setup

### Provision a Debian Instance

- Launch a Debian EC2 instance with at least 1GB RAM (t2.micro or larger)
![EC2 basic config](https://raw.githubusercontent.com/iamprecieee/freeswitch-setup/main/screenshots/Screenshot1.png)
- Configure Security Group with the following ports:
    - SSH (22) - TCP
    - SIP (5080) - TCP and UDP
    - RTP Media (16384-32768) - UDP
    ![Security group config](https://raw.githubusercontent.com/iamprecieee/freeswitch-setup/main/screenshots/Screenshot2.png)

### Configure Security Group

```bash
# From AWS Console:
# EC2 Dashboard > Network Settings > Security Groups > Edit inbound rules > Add rule
# Rule 1: Custom TCP, Port 5080, Source 0.0.0.0/0
# Rule 2: Custom UDP, Port 5080, Source 0.0.0.0/0
# Rule 3: Custom UDP, Port Range 16384-32768, Source 0.0.0.0/0
```


### Connect to Your Instance
```bash
# Create your SSH key pair file and paste in the private key used in provisioning your instance.
sudo nano ~/.ssh/key.pem

# Set your SSH key to not publicly viewable
chmod 400 ~/.ssh/your-key.pem

# Start SSH agent and add your key
eval "$(ssh-agent -s)"
ssh-add ~/.ssh/your-key.pem

# Connect to your instance
ssh -i "~/.ssh/your-key.pem" admin@your-ec2-public-dns
```

## FreeSWITCH Installation

### Update System and Install Dependencies

```bash
# Update system packages
sudo apt update && sudo apt upgrade -y

# Install dependencies
sudo apt install -yq git curl wget build-essential pkg-config libssl-dev \
  protobuf-compiler python3 python3-pip unzip python3-venv swig \
  postgresql postgresql-contrib redis-server gnupg2 lsb-release ffmpeg gpg
```

### Add SignalWire Repository

```bash
# Get a SignalWire token from https://signalwire.com
TOKEN=YOURSIGNALWIRETOKEN  # Replace with your actual token

# Download repository key
sudo wget --http-user=signalwire --http-password=$TOKEN \
  -O /usr/share/keyrings/signalwire-freeswitch-repo.gpg \
  https://freeswitch.signalwire.com/repo/deb/debian-release/signalwire-freeswitch-repo.gpg

# Configure authentication
echo "machine freeswitch.signalwire.com login signalwire password $TOKEN" | sudo tee /etc/apt/auth.conf
sudo chmod 600 /etc/apt/auth.conf

# Add repository sources
echo "deb [signed-by=/usr/share/keyrings/signalwire-freeswitch-repo.gpg] \
  https://freeswitch.signalwire.com/repo/deb/debian-release/ `lsb_release -sc` main" | \
  sudo tee /etc/apt/sources.list.d/freeswitch.list

echo "deb-src [signed-by=/usr/share/keyrings/signalwire-freeswitch-repo.gpg] \
  https://freeswitch.signalwire.com/repo/deb/debian-release/ `lsb_release -sc` main" | \
  sudo tee -a /etc/apt/sources.list.d/freeswitch.list

# Update package lists
sudo apt update
```
- `YOURSIGNALWIRETOKEN` can be created/retrieved from the signalwire dashboard under "personal access tokens".
![Signalwire profile dropdown](https://raw.githubusercontent.com/iamprecieee/freeswitch-setup/main/screenshots/Screenshot3.png) ![Create PAT](https://raw.githubusercontent.com/iamprecieee/freeswitch-setup/main/screenshots/Screenshot4.png)

### Install FreeSWITCH from Source

```bash
# Install build dependencies
sudo apt -y build-dep freeswitch

# Clone the repository
cd /usr/src
sudo git clone https://github.com/signalwire/freeswitch.git -bv1.10 freeswitch
cd freeswitch
sudo chown -R admin:admin /usr/src/freeswitch

# Configure and build
git config pull.rebase true
./bootstrap.sh -j
./configure
make
sudo make install

# Install sound files
sudo make cd-sounds-install cd-moh-install
```

### Set Owner and Permissions

```bash
cd /usr/local
sudo groupadd freeswitch
sudo adduser --quiet --system --home /usr/local/freeswitch --gecos "FreeSWITCH open source softswitch" \
  --ingroup freeswitch freeswitch --disabled-password
sudo chown -R freeswitch:freeswitch /usr/local/freeswitch/
sudo chmod -R ug=rwX,o= /usr/local/freeswitch/
sudo chmod -R u=rwx,g=rx /usr/local/freeswitch/bin
```

### Configure systemd Service

```bash
# Create service file
sudo tee /etc/systemd/system/freeswitch.service > /dev/null << 'EOF'
[Unit]
Description=FreeSWITCH
After=syslog.target network.target local-fs.target

[Service]
Type=forking
PIDFile=/usr/local/freeswitch/run/freeswitch.pid
PermissionsStartOnly=true
ExecStartPre=/bin/mkdir -p /usr/local/freeswitch/run
ExecStartPre=/bin/chown freeswitch:daemon /usr/local/freeswitch/run
ExecStart=/usr/local/freeswitch/bin/freeswitch -ncwait -nonat
TimeoutSec=45s
Restart=always
WorkingDirectory=/usr/local/freeswitch/run
User=freeswitch
Group=daemon
LimitCORE=infinity
LimitNOFILE=100000
LimitNPROC=60000
LimitRTPRIO=infinity
LimitRTTIME=7000000
IOSchedulingClass=realtime
IOSchedulingPriority=2
CPUSchedulingPolicy=rr
CPUSchedulingPriority=89
UMask=0007

[Install]
WantedBy=multi-user.target
EOF

# Enable and start FreeSWITCH
sudo systemctl daemon-reload
sudo systemctl start freeswitch
sudo systemctl enable freeswitch
sudo systemctl status freeswitch
```

### Set up fs_cli Access

```bash
# Add FreeSWITCH bin to path
sudo tee -a ~/.bash_profile > /dev/null << 'EOF'
PATH=$PATH:$HOME/bin
PATH=$PATH:/usr/local/freeswitch/bin
export PATH
EOF

# Apply changes
source ~/.bash_profile
```

### Setup DNS cashing

By default, Debian has no DNS caching and every lookup goes to the server from `/etc/resolv.conf`. Unbound is a light, secure, and easy to use DNS caching server.

```bash
sudo apt -y install unbound
sudo systemctl start unbound
sudo systemctl enable unbound
```

## FreeSWITCH Configuration

### Set a secure password

```bash
# Replace 'YourSecurePassword' with a strong password
sudo sed -i 's/default_password=.*/default_password=YourSecurePassword/' /usr/local/freeswitch/conf/vars.xml
```

### Set the external IP

```bash
# Replace 'YOUR_SERVER_PUBLIC_IP' with your EC2 instance's public IP
sudo sed -i "s/local_ip_v4=.*/local_ip_v4=YOUR_SERVER_PUBLIC_IP/" /usr/local/freeswitch/conf/vars.xml
```

## Twilio SIP Trunk Setup

### Create a Twilio Account

- Sign up at Twilio.com
- Get a phone number from your Twilio Console
![Get twilio number](https://raw.githubusercontent.com/iamprecieee/freeswitch-setup/main/screenshots/Screenshot5.png)

### Configure Elastic SIP Trunking

- From your Twilio Console, navigate to "Explore Products" → "Super Network" → "Elastic SIP Trunking"
![Elastic SIP trunking section](https://raw.githubusercontent.com/iamprecieee/freeswitch-setup/main/screenshots/Screenshot6.png)
- Click on "Trunks" and create a new SIP trunk with a descriptive name
![Trunk](https://raw.githubusercontent.com/iamprecieee/freeswitch-setup/main/screenshots/Screenshot7.png)

### Configure your trunk:

#### Termination (Outbound Calling)
- In your trunk menu, go to "Termination"
![Termination](https://raw.githubusercontent.com/iamprecieee/freeswitch-setup/main/screenshots/Screenshot8.png)
- Create a Termination SIP URI (e.g., "freeswitchtest")
- Under "Authentication", create a new IP Access Control List:
    - Add a friendly name
    - Enter your EC2 instance's public IP with CIDR /32
    - Save the configuration
    ![IP ACL](https://raw.githubusercontent.com/iamprecieee/freeswitch-setup/main/screenshots/Screenshot9.png)

#### Origination (Inbound Calling)
- In your trunk menu, go to "Origination"
- Add a new Origination URI in the format: `sip:YOUR_SERVER_PUBLIC_IP`
- Save the configuration
![Origination setup](https://raw.githubusercontent.com/iamprecieee/freeswitch-setup/main/screenshots/Screenshot10.png)

#### Assign Phone Numbers
- In your trunk menu, go to "Numbers"
- Click "Add a Number" → "Add an Existing Number"
- Select your Twilio phone number

## Configure FreeSWITCH for Twilio

### Create the Twilio trunk configuration file

```bash
sudo tee /usr/local/freeswitch/conf/sip_profiles/external/twilio.xml > /dev/null << 'EOF'
<include>
  <gateway name="twilio">
    <param name="proxy" value="YOUR_TERMINATION_SIP_URI.pstn.twilio.com"/>
    <param name="realm" value="YOUR_TERMINATION_SIP_URI.pstn.twilio.com"/>
    <param name="register" value="false"/>
    <param name="from-user" value="YOUR_TWILIO_PHONE_NUMBER"/>
    <param name="from-domain" value="YOUR_TERMINATION_SIP_URI.pstn.twilio.com"/>
    <param name="username" value="YOUR_ACCOUNT_SID"/>
    <param name="password" value="YOUR_AUTH_TOKEN"/>
    <param name="codec-prefs" value="PCMU,PCMA"/>
    <param name="dtmf-type" value="rfc2833"/>
  </gateway>
</include>
EOF
```
Replace the following placeholders:
-  YOUR_TERMINATION_SIP_URI: The name you created in the Termination step (e.g., "freeswitchtest")
- YOUR_TWILIO_PHONE_NUMBER: Your Twilio phone number in E.164 format (e.g., +18149998410)
- YOUR_ACCOUNT_SID: Found in your Twilio Console dashboard
- YOUR_AUTH_TOKEN: Found in your Twilio Console dashboard

### Reload FreeSWITCH Configuration

```bash
# Connect to FreeSWITCH CLI
sudo chmod +x /usr/local/freeswitch/bin/fs_cli
sudo usermod -aG freeswitch admin
export PATH=/usr/local/freeswitch/bin:$PATH
source ~/.bashrc
# Log out and log back in to save changes
fs_cli

# Inside the FreeSWITCH CLI, reload the SIP profile
sofia profile external restart
```

## Integration Testing

### Test the Twilio Gateway Connection

```bash
# Check gateway status
fs_cli -x "sofia status gateway twilio"
```
You should see the gateway status as "UP".

### Make a Test Call

For Twilio trial accounts, you must first verify any phone number you want to call:
- Go to your Twilio Console → Phone Numbers → Verified Caller IDs
- Add and verify each destination number before testing

```bash
# Make a test call (replace with a verified number)
fs_cli -x "originate {ignore_early_media=true,origination_caller_id_number=YOUR_TWILIO_NUMBER}sofia/gateway/twilio/YOUR_VERIFIED_PHONE_NUMBER &echo"
```

```bash
# Format for E.164 (with country code, no spaces or hyphens)
fs_cli -x "originate {ignore_early_media=true,origination_caller_id_number=YOUR_TWILIO_NUMBER}sofia/gateway/twilio/YOUR_VERIFIED_PHONE_NUMBER 1000 XML Twilio_Inbound"
```

# Testing outbound calls

## Set up call script (`/home/admin/call.py`)
- Here's a sample call script:
```python
import ESL, subprocess, os, time, json, base64
from pathlib import Path

# FreeSWITCH ESL Configuration
FREESWITCH_HOST = "127.0.0.1"
FREESWITCH_PORT = 8021
FREESWITCH_PASSWORD = "ClueCon"

# Temporary Storage Path for MP3 Files
TEMP_DIR = Path("/tmp/mp3_uploads")
TEMP_DIR.mkdir(parents=True, exist_ok=True)

# Recording directory with proper permissions
RECORDINGS_DIR = Path("/tmp/freeswitch_recordings")
RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)

PHONE_NUMBER = "+1234567890" # Replace with your twilio verified caller id
CALLER_ID = "+1234567890" # Replace with your twilio number
FILE_PATH = Path("/home/admin/Wav.1.m4a") # Replace with path to your uploaded audio file
GATEWAY = "twilio"

def make_outbound_call(phone_number, caller_id, file_path, gateway="twilio2"):
    """
    Make an outbound call and play an MP3 file when answered.
    Also record the call.
    """
    m4a_file_path = file_path
    wav_path = None

    # Initiate connection to freeswitch
    conn = ESL.ESLconnection(FREESWITCH_HOST, FREESWITCH_PORT, FREESWITCH_PASSWORD)
    if not conn.connected():
        print("Failed to connect to FreeSWITCH")
        return False

    try:
        # Create recordings directory with proper permissions
        recordings_dir = str(RECORDINGS_DIR)
        os.makedirs(recordings_dir, exist_ok=True)

        # Set proper permissions - important for FreeSWITCH
        subprocess.call(["sudo", "chmod", "777", recordings_dir])  # More permissive for testing

        # Try to set ownership if possible (requires sudo privileges)
        try:
            subprocess.call(["sudo", "chown", "freeswitch:freeswitch", recordings_dir])
        except Exception as e:
            print(f"Could not change ownership, but continuing: {str(e)}")

        # Ensure M4A file exists
        if not os.path.exists(m4a_file_path):
            print(f"M4A file not found: {m4a_file_path}")
            return False

        # Convert M4A to WAV (FreeSWITCH prefers WAV)
        wav_path = m4a_file_path.with_suffix(".wav")
        subprocess.call(["ffmpeg", "-i", m4a_file_path, "-ar", "8000", "-ac", "1", "-f", "wav", wav_path, "-y"])
        subprocess.call(["sudo", "chmod", "777", wav_path])  # Ensure file is readable by FreeSWITCH

        # Set channel variables for recording
        origination_vars = {
            "absolute_codec_string": "PCMA",
            "ignore_early_media": "false",
            "origination_caller_id_number": caller_id,
            "RECORD_STEREO": "false",
            "RECORD_SOFTWARE": "true"  # Use software recording instead of hardware
        }

        # Format channel variables
        vars_string = ",".join([f"{k}={v}" for k, v in origination_vars.items()])

        # Initiate the call with park application
        call_command = (
           f"originate {{{vars_string}}}"
           f"sofia/gateway/{gateway}/{phone_number} "
           f"&park()"
        )

        print(f"Initiating call to {phone_number}")
        result = conn.api(call_command)
        response = result.getBody().strip()

        if "+OK" in response:
            call_uuid = response.replace("+OK ", "")
            print(f"Call initiated successfully with UUID: {call_uuid}")

            # Wait for call to be established
            print("Waiting for call to connect...")
            time.sleep(3)

            # Check if call is still active
            status_cmd = f"uuid_exists {call_uuid}"
            status = conn.api(status_cmd).getBody().strip()

            if "true" in status:
                print("Call connected, checking channel status...")

                # Verify call is actually answered
                channel_state_cmd = f"uuid_getvar {call_uuid} answer_state"
                channel_state = conn.api(channel_state_cmd).getBody().strip()
                print(f"Channel answer state: {channel_state}")

                if channel_state != "answered":
                    print("Waiting additional time for call to be fully answered...")
                    time.sleep(0.5)  # Give more time to ensure call is fully established

                # Create absolute recording path
                recording_filename = f"{call_uuid}.wav"
                recording_path = os.path.join(recordings_dir, recording_filename)
                print(f"Will record to: {recording_path}")

                # Ensure directory is writeable by testing with a small file
                test_file = os.path.join(recordings_dir, "test.txt")
                try:
                    with open(test_file, 'w') as f:
                        f.write("test")
                    os.remove(test_file)
                    print("Recording directory is writeable")
                except Exception as e:
                    print(f"Warning: Recording directory may not be writeable: {str(e)}")

                # Start recording with explicit format
                record_cmd = f"uuid_record {call_uuid} start {recording_path}"
                record_result = conn.api(record_cmd)
                print(f"Recording command result: {record_result.getBody().strip()}")

                # Verify recording started
                is_recording_cmd = f"uuid_getvar {call_uuid} is_recording"
                is_recording = conn.api(is_recording_cmd).getBody().strip()
                print(f"Is recording? {is_recording}")

                # Play the message
                print("Playing audio file...")
                play_cmd = f"uuid_broadcast {call_uuid} {wav_path} aleg"
                play_result = conn.api(play_cmd)
                print(f"Play command result: {play_result.getBody().strip()}")

                # Get audio file duration and add a buffer for safety
                audio_duration = get_audio_duration(wav_path)
                sleep_time = audio_duration + 1  # Add 1 seconds buffer
                print(f"Audio duration: {audio_duration}s, sleeping for {sleep_time}s")
                time.sleep(sleep_time)

                # Stop recording
                print("Stopping recording...")
                stop_record_cmd = f"uuid_record {call_uuid} stop {recording_path}"
                stop_result = conn.api(stop_record_cmd)
                print(f"Stop recording result: {stop_result.getBody().strip()}")

                # Check if recording file exists
                time.sleep(1)  # Brief pause to ensure file is written
                if os.path.exists(recording_path):
                    print(f"Recording saved successfully: {recording_path}")
                    file_size = os.path.getsize(recording_path)
                    print(f"Recording file size: {file_size} bytes")
                else:
                    print(f"Warning: Recording file not found at {recording_path}")
                    # List files in recording directory
                    print("Files in recording directory:")
                    for file in os.listdir(recordings_dir):
                        print(f"  {file}")

                # Gracefully end the call
                hangup_cmd = f"uuid_kill {call_uuid}"
                conn.api(hangup_cmd)
                print("Call ended")
                return True
            else:
                print("Call was answered but disconnected before audio file could play")
                return False
        else:
            print(f"Call failed: {response}")
            return False
    except Exception as e:
        print(f"Error: {str(e)}")
        return False
    finally:
        # Clean up audio files
        if wav_path and os.path.exists(wav_path):
            os.remove(wav_path)

def get_audio_duration(file_path):
    """Get the duration of an audio file in seconds using ffprobe"""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of",
             "default=noprint_wrappers=1:nokey=1", file_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        duration = float(result.stdout.strip())
        return duration
    except Exception as e:
        print(f"Error getting audio duration: {str(e)}")
        return 7  # Default duration if cannot determine


if __name__ == "__main__":
    make_outbound_call(PHONE_NUMBER, CALLER_ID, FILE_PATH, gateway=GATEWAY)
```

## Create and activate venv
```bash
python3 -m venv venv
source ./venv/bin/activate
# Install python-ESL
pip install python-ESL
```

## Run call script
```bash
python3 /home/admin/call.py
```


### ⚠️ For python-ESL error:
- If SWIG 4.x is installed from your package manager, you may need to remove it or ensure that your PATH prioritizes the newly built SWIG.
```bash
sudo apt-get remove swig
```

- Download SWIG 3.0.12.
```bash
sudo wget https://downloads.sourceforge.net/project/swig/swig/swig-3.0.12/swig-3.0.12.tar.gz
```

- Extract and Build SWIG 3.0.12.
```bash
tar -xzvf swig-3.0.12.tar.gz
cd swig-3.0.12
./configure
make
sudo make install
```

- Verify installation.
```bash
swig -version
```

- Reinstall python-ESL.
```bash
pip install python-ESL
```