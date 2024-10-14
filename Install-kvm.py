import os
import subprocess

# Function to run shell commands with error handling
def run_command(command, exit_on_failure=True):
    try:
        subprocess.run(command, shell=True, check=True)
    except subprocess.CalledProcessError as e:
        print(f"\033[91mError executing command: {e}\033[0m")  # Red color for error messages
        if exit_on_failure:
            exit(1)

# Check if essential commands are available
def check_command_exists(command):
    if subprocess.call(f"type {command}", shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE) != 0:
        print(f"\033[91m{command} is not installed or not in the system's PATH.\033[0m")  # Red color for error messages
        exit(1)

# Ensure the script is only run on Rocky 9
def check_os_version():
    try:
        with open('/etc/os-release') as f:
            os_release_info = f.read()
        if 'Rocky' not in os_release_info or '9' not in os_release_info:
            print("\033[91mThis script is only intended for Rocky Linux 9. Exiting.\033[0m")  # Red color for error messages
            exit(1)
    except FileNotFoundError:
        print("\033[91mUnable to detect OS version. Ensure you are running Rocky Linux 9.\033[0m")  # Red color for error messages
        exit(1)

# Check the OS version before running the rest of the script
check_os_version()

# List of essential commands to check
required_commands = ["nmcli", "dnf", "hostnamectl"]
for cmd in required_commands:
    check_command_exists(cmd)

# Get host name input
host_name = input("Input new host name of this server: ")

# Update hostname
run_command(f"hostnamectl set-hostname {host_name}")

# Disable IPv6 in /etc/hosts
with open('/etc/hosts', 'r+') as f:
    hosts = f.read()
    if '::1' in hosts:
        hosts = hosts.replace('::1', '#::1')
        f.seek(0)
        f.write(hosts)
        f.truncate()

# Update the OS and install virtualization packages
run_command("dnf install -y epel-release")
run_command("dnf update -y")
run_command("dnf install qemu-kvm libvirt virt-manager virt-install virt-top libguestfs-tools bridge-utils virt-viewer -y")

# Start and enable libvirt service
run_command("systemctl enable --now libvirtd")

# Gather network information
ip_addr = subprocess.getoutput("hostname -I | awk '{print $1}'")
gateway = subprocess.getoutput("/sbin/ip route | awk '/default/ { print $3 }' | head -1")
dns1 = subprocess.getoutput("grep nameserver /etc/resolv.conf | sed -n 1p | awk '{print $2}'")
dns2 = subprocess.getoutput("grep nameserver /etc/resolv.conf | sed -n 2p | awk '{print $2}'")

# Create the bridge using nmcli
run_command("nmcli connection add type bridge autoconnect yes con-name br0 ifname br0")
run_command(f"nmcli connection modify br0 ipv4.addresses {ip_addr}/24 ipv4.gateway {gateway} ipv4.dns {dns1} +ipv4.dns {dns2} ipv4.method manual")

# Bring up the bridge
run_command("nmcli connection up br0")

# List active network interfaces
network_interfaces = subprocess.getoutput("nmcli device status | grep connected | awk '{print $1}'")
print("Available network interfaces:\n" + network_interfaces)

# Get the interface to be added to the bridge
interface = input("Please input the network interface you want to add to the bridge (e.g., eth0, enp3s0, etc): ")

# Add the selected interface to the bridge
run_command(f"nmcli connection add type bridge-slave autoconnect yes con-name {interface}-slave ifname {interface} master br0")

# Bring up the bridge again after adding the interface
run_command("nmcli connection up br0")

# Prompt to reboot
input("The installation of KVM ends now and OS needs to be rebooted. Press any key to reboot the OS...")

# Reboot the system
run_command("reboot")
