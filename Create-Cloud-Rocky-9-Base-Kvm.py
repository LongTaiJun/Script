import os
import subprocess
import tempfile
import crypt
import urllib.request
import re
import sys

def print_in_yellow(message):
    """Print message in yellow color."""
    print(f"\033[93m{message}\033[0m")

def check_root():
    """Check if the script is being run as root."""
    if os.geteuid() != 0:
        print_in_yellow("This script must be run as root. Exiting.")
        sys.exit(1)

def validate_ip_suffix(ip_suffix):
    """Validate that ip_suffix is a number between 1 and 254."""
    if not ip_suffix.isdigit() or not (1 <= int(ip_suffix) <= 254):
        print("Error: IP suffix must be a number between 1 and 254.")
        return False
    return True

def validate_password(password):
    """Validate password is at least 6 characters and has no spaces."""
    if len(password) < 6 or " " in password:
        print("Error: Password must be at least 6 characters long and contain no spaces.")
        return False
    return True

def validate_vm_name(vm_name):
    """Validate VM name contains only letters, numbers, and hyphen, and is not purely numeric."""
    if not re.match("^[A-Za-z0-9-]+$", vm_name):
        print("Error: VM name can only contain letters, numbers, and hyphen (-).")
        return False
    if vm_name.isdigit():
        print("Error: VM name cannot be purely numeric.")
        return False
    return True

def validate_cpu(cpu):
    """Validate CPU count is between 1 and 16."""
    if not cpu.isdigit() or not (1 <= int(cpu) <= 16):
        print("Error: CPU must be a number between 1 and 16.")
        return False
    return True

def validate_memory(memory):
    """Validate memory size is between 1 and 32 GB."""
    if not memory.isdigit() or not (1 <= int(memory) <= 32):
        print("Error: Memory must be a number between 1 and 32 GB.")
        return False
    return True

def validate_disk_size(disk_size):
    """Validate disk size is between 10 and 2048 GB."""
    if not disk_size.isdigit() or not (10 <= int(disk_size) <= 2048):
        print("Error: Disk size must be a number between 10 and 2048 GB.")
        return False
    return True

def download_image(image_url, image_path):
    """Download the image file and show progress."""
    try:
        print(f"Downloading image from {image_url}")

        # Get the file size
        with urllib.request.urlopen(image_url) as response:
            total_size = int(response.getheader('Content-Length', 0))
            downloaded_size = 0
            chunk_size = 1024

            with open(image_path, 'wb') as out_file:
                while True:
                    chunk = response.read(chunk_size)
                    if not chunk:
                        break
                    out_file.write(chunk)
                    downloaded_size += len(chunk)

                    # Calculate and display progress
                    done = int(50 * downloaded_size / total_size)
                    print(f"\r[{'=' * done}{' ' * (50 - done)}] {downloaded_size}/{total_size} bytes", end='')

        print("\nDownload complete")

        # Verify the downloaded file size
        if os.path.getsize(image_path) != total_size:
            print("File size mismatch, download might be incomplete")
            return False

    except Exception as e:
        print(f"Failed to download image: {e}")
        return False
    return True

def get_image_url_by_ip(host_ip):
    """Get the appropriate image URL based on the IP address."""
    if host_ip.startswith("192.168.100"):
        return "http://192.168.100.10:8000/images/Rocky-9-GenericCloud-Base.latest.x86_64.qcow2"
    else:
        return "http://download.rockylinux.org/pub/rocky/9/images/x86_64/Rocky-9-GenericCloud.latest.x86_64.qcow2"

def get_host_ip():
    """Get the host IP address using hostname -I."""
    try:
        result = subprocess.check_output(["hostname", "-I"]).decode().strip()
        ip = result.split()[0]  # Get the first IP address
        return ip
    except subprocess.CalledProcessError as e:
        print(f"Unable to get host IP address: {e}")
        return None

def get_default_gateway():
    """Get the system's default gateway"""
    try:
        result = subprocess.check_output(["ip", "route", "show", "default"]).decode().strip()
        gateway = result.split()[2]  # Get the default gateway address
        return gateway
    except subprocess.CalledProcessError as e:
        print(f"Unable to get default gateway: {e}")
        return None

def create_cloud_init_iso(vm_name, password, ip_address, gateway):
    """Create a cloud-init ISO file with network and user configuration."""
    try:
        # Generate encrypted password
        encrypted_password = crypt.crypt(password, crypt.mksalt(crypt.METHOD_SHA512))

        # Determine DNS servers based on IP address
        if ip_address.startswith("192.168.100"):
            dns_servers = "223.5.5.5 223.6.6.6"
        else:
            dns_servers = "8.8.8.8 8.8.4.4"

        # Create cloud-init configuration file
        user_data = f"""#cloud-config
packages:
  - vim
  - telnet
  - epel-release
users:
  - name: rocky
    ssh-authorized-keys: []
    lock_passwd: false
    passwd: {encrypted_password}
chpasswd:
  expire: false
ssh_pwauth: true
runcmd:
  - |
    interface=$(nmcli -t -f NAME,DEVICE connection show | head -n 1 | awk -F ':' '{{print $1}}')
    nmcli connection modify "$interface" ipv4.addresses {ip_address}/24
    nmcli connection modify "$interface" ipv4.gateway {gateway}
    nmcli connection modify "$interface" ipv4.dns "{dns_servers}"
    nmcli connection modify "$interface" ipv4.method manual
    nmcli connection up "$interface"
    root_partition=$(findmnt -n -o SOURCE /)
    disk_device=$(echo $root_partition | sed -E 's/[0-9]+$//')
    partition_number=$(echo $root_partition | grep -o '[0-9]*$')
    growpart $disk_device $partition_number
    if lsblk -f | grep -q 'ext4'; then
        resize2fs $root_partition
    elif lsblk -f | grep -q 'xfs'; then
        xfs_growfs /
    fi
"""

        meta_data = f"""instance-id: {vm_name}
local-hostname: {vm_name}
"""

        # Use a temporary directory to store cloud-init files
        with tempfile.TemporaryDirectory() as tmpdir:
            user_data_path = os.path.join(tmpdir, "user-data")
            meta_data_path = os.path.join(tmpdir, "meta-data")
            
            with open(user_data_path, "w") as ud_file:
                ud_file.write(user_data)
            
            with open(meta_data_path, "w") as md_file:
                md_file.write(meta_data)
            
            # Create ISO file
            iso_path = os.path.join("/var/lib/libvirt/images/", f"{vm_name}-cloud-init.iso")
            subprocess.run(["genisoimage", "-output", iso_path, "-volid", "cidata", "-joliet", "-rock", user_data_path, meta_data_path], check=True)
            
            return iso_path

    except Exception as e:
        print(f"Failed to create cloud-init ISO file: {e}")
        return None

def create_vm(ip_suffix, password, vm_name, cpu, memory, image_url, disk_size):
    """Create a virtual machine."""
    try:
        # Get host IP and gateway
        host_ip = get_host_ip()
        if not host_ip:
            print("Unable to get host IP, VM creation aborted.")
            return

        base_ip = ".".join(host_ip.split(".")[:3])  # Get the first three octets
        ip_address = f"{base_ip}.{ip_suffix}"

        gateway = get_default_gateway()
        if not gateway:
            print("Unable to get gateway, VM creation aborted.")
            return

        # Check if image exists or download it
        image_path = "/root/Downloads/Rocky-9-GenericCloud.latest.x86_64.qcow2"
        if not os.path.exists(image_path):
            print(f"Image not found, downloading from {image_url}")
            if not download_image(image_url, image_path):
                print("Image download failed, VM creation aborted.")
                return

        # Copy the image and resize disk
        dest_image_path = f"/var/lib/libvirt/images/{vm_name}.qcow2"
        subprocess.run(["cp", image_path, dest_image_path], check=True)
        subprocess.run(["qemu-img", "resize", dest_image_path, disk_size], check=True)

        # Create cloud-init ISO
        cloud_init_iso = create_cloud_init_iso(vm_name, password, ip_address, gateway)
        if not cloud_init_iso:
            print("Failed to create cloud-init ISO, VM creation aborted.")
            return

        # Create the VM
        subprocess.run([
            "virt-install", "--name", vm_name,
            "--vcpus", str(cpu), "--memory", str(memory * 1024),
            f"--disk=path={dest_image_path},format=qcow2",
            f"--disk=path={cloud_init_iso},device=cdrom",
            "--os-variant=rocky9",
            "--network", "bridge=br0,model=virtio",
            "--boot", "hd", "--noautoconsole", "--import"
        ], check=True)

        print("\n" + "="*40)
        print(f"VM '{vm_name}' created successfully!")
        print(f"IP Address: {ip_address}")
        print(f"CPU: {cpu}")
        print(f"Memory: {memory} GB")
        print(f"Disk: {disk_size} GB")
        print(f"Username: rocky")
        print(f"Password: {password}")
        print("="*40 + "\n")

    except subprocess.CalledProcessError as e:
        print(f"Error during VM creation: {e}")
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    check_root()
    
    while True:
        ip_suffix = input("Enter the last octet of the IP address (1-254): ")
        if validate_ip_suffix(ip_suffix):
            break

    while True:
        password = input("Enter the password for the VM (min 6 chars, no spaces): ")
        if validate_password(password):
            break

    while True:
        vm_name = input("Enter the VM name (letters, numbers, and hyphen only): ")
        if validate_vm_name(vm_name):
            break

    while True:
        cpu = input("Enter the number of CPUs (1-16): ")
        if validate_cpu(cpu):
            break

    while True:
        memory = input("Enter the amount of memory in GB (1-32): ")
        if validate_memory(memory):
            break

    while True:
        disk_size = input("Enter the disk size in GB (10-2048): ")
        if validate_disk_size(disk_size):
            break

    image_url = get_image_url_by_ip(get_host_ip())

    create_vm(ip_suffix, password, vm_name, int(cpu), int(memory), image_url, f"{disk_size}G")
