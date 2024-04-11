#!/bin/bash

# environment variables
CLUSTER_NAME="test-cluster"
ES_PASSWD="test.com@123"
DATA_DIR="/data/elasticsearch/data"
CONF_DIR="/etc/elasticsearch"
LOG_DIR="/data/elasticsearch/logs"
ES_CONFIG_FILE="$CONF_DIR/elasticsearch.yml"
IP_ADDRESS=$(hostname -I | awk '{print $1}' | head -n 1)

if [[ $1 = slave ]]; then
  read -r -e -p "Please enter the token generated by the master node to join the cluster: " ES_TOKEN
fi

read -r -e -p $'Please enter all elasticsearch node IP addresses\nExample: 192.168.100.10, 192.168.100.11, 192.168.100.12\n:' ES_CLUSTER_IP

function init_system() {
  # install software
  yum install expect -y
  # disable swap
  swapoff -a
  desired_swappiness=1
  current_swappiness=$(sysctl -n vm.swappiness)
  if [ "$current_swappiness" != "$desired_swappiness" ]; then
    echo "vm.swappiness=$desired_swappiness" | tee -a /etc/sysctl.conf >/dev/null
    sysctl -p >/dev/null
  fi
  # check if vm.max_map_count exists in sysctl.conf file
  if grep -q '^vm.max_map_count' /etc/sysctl.conf; then
    # if exists, update the value to 262144
    sudo sed -i 's/^vm.max_map_count.*/vm.max_map_count=262144/g' /etc/sysctl.conf
  else
    # if does not exist, append the value to the end of the file
    echo 'vm.max_map_count=262144' | tee -a /etc/sysctl.conf >/dev/null
  fi
  # reload the sysctl.conf file
  sudo sysctl -p
  # disable firewall and iptables
  systemctl disable firewalld.service
  systemctl stop firewalld.service
  # disable selinux
  sed -i 's/^SELINUX=.*/SELINUX=permissive/g' /etc/selinux/config
  setenforce 0
  # configure system ulimit parameter
  for file in /etc/security/limits.d/*nproc.conf; do
    if [ -e "$file" ]; then
      rename nproc.conf nproc.conf_bk /etc/security/limits.d/*nproc.conf
      break
    fi
  done
  sed -i '/^# End of file/,$d' /etc/security/limits.conf
  cat >>/etc/security/limits.conf <<EOF
# End of file
* soft nproc 1000000
* hard nproc 1000000
* soft nofile 1000000
* hard nofile 1000000
* soft memlock unlimited
* hard memlock unlimited
EOF
}

function install_jdk() {
  cat <<EOF | tee /etc/yum.repos.d/adoptium.repo >/dev/null
[elasticsearch]
name=Elasticsearch repository for 8.x packages
baseurl=https://artifacts.elastic.co/packages/8.x/yum
gpgcheck=0
gpgkey=https://artifacts.elastic.co/GPG-KEY-elasticsearch
enabled=0
autorefresh=1
type=rpm-md
EOF
  yum install -y temurin-11-jdk

}

function install_elasticsearch() {
  # remove elasticsearch old file
  rm -rf /etc/elasticsearch /var/lib/elasticsearch /usr/share/elasticsearch /data/elasticsearch
  # import the elasticsearch gpg Key
  rpm --import https://artifacts.elastic.co/GPG-KEY-elasticsearch
  # install from the rpm repository
  cat <<EOF | tee /etc/yum.repos.d/elasticsearch.repo >/dev/null
[elasticsearch]
name=Elasticsearch repository for 8.x packages
baseurl=https://artifacts.elastic.co/packages/8.x/yum
gpgcheck=0
gpgkey=https://artifacts.elastic.co/GPG-KEY-elasticsearch
enabled=0
autorefresh=1
type=rpm-md
EOF
  # install elasticsearch
  yum install --enablerepo=elasticsearch elasticsearch -y
  # create data directory
  mkdir -p $DATA_DIR $LOG_DIR
  chown -R elasticsearch.elasticsearch $DATA_DIR $LOG_DIR
  # start elasticsearch on boot
  systemctl enable elasticsearch.service
}

function configure_elasticsearch_master() {
  # backup elasticsearch config
  cp -rf "$ES_CONFIG_FILE" "$ES_CONFIG_FILE"."$(date +"%Y%m%d%H%M%S")".bak
  # modify elasticsearch data storage directory
  sed -i "s|^path.data: /var/lib/elasticsearch$|path.data: $DATA_DIR|" "$ES_CONFIG_FILE"
  # modify elasticsearch logs storage directory
  sed -i "s|^path.logs: /var/log/elasticsearch$|path.logs: $LOG_DIR|" "$ES_CONFIG_FILE"
  # set elasticsearch default port
  sed -i 's/^#http.port: 9200/http.port: 9200/' "$ES_CONFIG_FILE"
  # set elasticsearch node name
  sed -i "s/^#node.name: .*/node.name: $(hostname)/" "$ES_CONFIG_FILE"
  # set elasticsearch cluster name
  sed -i "s/^#cluster.name: my-application/cluster.name: $CLUSTER_NAME/" "$ES_CONFIG_FILE"
  # set elasticsearch transport address
  sed -i 's/^#transport.host:.*$/transport.host: 0.0.0.0/' "$ES_CONFIG_FILE"
  # set elasticsearch listening address
  sed -i 's/^#network.host:.*$/network.host: 0.0.0.0/' "$ES_CONFIG_FILE"
  # discover the hosts of other nodes in the cluster on startup
  # discovery.seed_hosts: "elk-cluster-001, elk-cluster-002, elk-cluster-003"
  sed -i "s/^#discovery.seed_hosts:.*$/discovery.seed_hosts: [$ES_CLUSTER_IP]/" "$ES_CONFIG_FILE"
  # define initial masters, assuming a cluster size of at least 3
  # cluster.initial_master_nodes: "elk-cluster-001, elk-cluster-002, elk-cluster-003"
  # check if http.cors related content already exists
  if ! grep -q "^http.cors" "$ES_CONFIG_FILE"; then
    # if it does not exist, add http.cors related parameters to the configuration file
    cat <<EOF >>"$ES_CONFIG_FILE"
http.cors.enabled: true
http.cors.allow-origin: "*"
http.cors.allow-credentials: true
http.cors.allow-headers: "X-Requested-With, Content-Type, Content-Length, Authorization"
EOF
  fi
  # start elasticsearch
  systemctl start elasticsearch.service
  # use expect to perform interactive operations to reset elasticsearch passwords
  sleep 5
  expect <<EOF
    spawn /usr/share/elasticsearch/bin/elasticsearch-reset-password -u elastic -i
    expect "Please confirm that you would like to continue" {
        send "y\r"
    }
    expect "Enter password" {
        send "$ES_PASSWD\r"
    }
    expect "Re-enter password" {
        send "$ES_PASSWD\r"
    }
    expect eof
EOF
  # create cluster verification token
  /usr/share/elasticsearch/bin/elasticsearch-create-enrollment-token -s node >/tmp/elasticsearch_cluster_token.txt
  echo -e "elasticsearch master token:\n$(cat /tmp/elasticsearch_cluster_token.txt)"
  # check elasticsearch service status
  systemctl status elasticsearch.service | grep "Active:"
}

function configure_elasticsearch_slave() {
  # backup elasticsearch config
  cp -rf "$ES_CONFIG_FILE" "$ES_CONFIG_FILE"."$(date +"%Y%m%d%H%M%S")".bak
  # modify elasticsearch data storage directory
  sed -i "s|^path.data: /var/lib/elasticsearch$|path.data: $DATA_DIR|" "$ES_CONFIG_FILE"
  # modify elasticsearch logs storage directory
  sed -i "s|^path.logs: /var/log/elasticsearch$|path.logs: $LOG_DIR|" "$ES_CONFIG_FILE"
  # set elasticsearch default port
  sed -i 's/^#http.port: 9200/http.port: 9200/' "$ES_CONFIG_FILE"
  # set elasticsearch node name
  sed -i "s/^#node.name: .*/node.name: $(hostname)/" "$ES_CONFIG_FILE"
  # set elasticsearch cluster name
  sed -i "s/^#cluster.name: my-application/cluster.name: $CLUSTER_NAME/" "$ES_CONFIG_FILE"
  # set elasticsearch transport address
  sed -i 's/^#transport.host:.*$/transport.host: 0.0.0.0/' "$ES_CONFIG_FILE"
  # set elasticsearch listening address
  sed -i 's/^#network.host:.*$/network.host: 0.0.0.0/' "$ES_CONFIG_FILE"
  # discover the hosts of other nodes in the cluster on startup
  sed -i "s/^#discovery.seed_hosts:.*$/discovery.seed_hosts: [$ES_CLUSTER_IP]/" "$ES_CONFIG_FILE"
  # define initial masters, assuming a cluster size of at least 3
  # cluster.initial_master_nodes: "elk-cluster-001, elk-cluster-002, elk-cluster-003"
  # check if http.cors related content already exists
  if ! grep -q "^http.cors" "$ES_CONFIG_FILE"; then
    # if it does not exist, add http.cors related parameters to the configuration file
    cat <<EOF >>"$ES_CONFIG_FILE"
http.cors.enabled: true
http.cors.allow-origin: "*"
http.cors.allow-credentials: true
http.cors.allow-headers: "X-Requested-With, Content-Type, Content-Length, Authorization"
EOF
  fi
  # join the cluster using the token generated by the master
  expect <<EOF
    spawn /usr/share/elasticsearch/bin/elasticsearch-reconfigure-node --enrollment-token $ES_TOKEN
    expect "Do you want to continue with the reconfiguration process" {
        send "y\r"
    }
    expect eof
EOF
  # start elasticsearch
  systemctl start elasticsearch.service
  # check elasticsearch service status
  systemctl status elasticsearch.service | grep "Active:"
}

function start_elasticsearch_service() {
  # start elasticsearch
  systemctl start elasticsearch.service
}

function stop_elasticsearch_service() {
  # stop elasticsearch
  systemctl stop elasticsearch.service
}

function restart_elasticsearch_service() {
  # restart elasticsearch
  systemctl restart elasticsearch.service
}

function main() {
  # view parameter
  if [ -z "$1" ]; then
    GREEN='\033[0;32m'
    NC='\033[0m'
    echo "please enter the corresponding parameters:"
    echo -e "${GREEN}master:${NC} init elasticsearch master node"
    echo -e "${GREEN}slave:${NC} init elasticsearch slave node"
    echo -e "${GREEN}start:${NC} start elasticsearch service"
    echo -e "${GREEN}stop:${NC} stop elasticsearch service"
    echo -e "${GREEN}restart:${NC} restart elasticsearch service"
    exit
  fi
  # command
  local cmd=${1}

  case "$cmd" in
  "master")
    # init system
    init_system
    # install jdk
    install_jdk
    # install elasticsearch
    install_elasticsearch
    # configure elasticsearch
    configure_elasticsearch_master
    ;;
  "slave")
    # init system
    init_system
    # install jdk
    install_jdk
    # install elasticsearch
    install_elasticsearch
    # configure elasticsearch
    configure_elasticsearch_slave
    ;;
  "start")
    start_elasticsearch_service
    ;;
  "stop")
    stop_elasticsearch_service
    ;;
  "restart")
    restart_elasticsearch_service
    ;;
  esac
}

main "$*"