# Static Host Configuration Files

This directory contains per-cluster host configuration files for the SDN controller.

## File Naming Convention

Each cluster should have its own configuration file:
- `hosts_cluster1.json` - Configuration for Cluster 1
- `hosts_cluster2.json` - Configuration for Cluster 2
- `hosts_clusterN.json` - Configuration for Cluster N

## File Format

Each configuration file is a JSON object with the following structure:

```json
{
  "cluster_id": 1,
  "hosts": {
    "10.10.0.10": {
      "mac": "02:da:d9:38:7b:b1",
      "port": 9,
      "dpid": "0x0c826821c8a4",
      "description": "Host h1 on OVS1"
    },
    "10.10.0.11": {
      "mac": "aa:bb:cc:dd:ee:ff",
      "port": 10,
      "dpid": "0x0c826821c8a4",
      "description": "Host h2 on OVS1"
    }
  }
}
```

### Field Descriptions

- **cluster_id** (integer): The cluster ID this configuration belongs to (must match filename)
- **hosts** (object): Dictionary mapping IP addresses to host configurations
  - **Key** (string): Host IP address (e.g., "10.10.0.10")
  - **Value** (object): Host configuration with the following fields:
    - **mac** (string): MAC address of the OVS port connecting to this host
    - **port** (integer): OVS port number where host is connected
    - **dpid** (string): Datapath ID of the OVS switch (hex string with 0x prefix or decimal)
    - **description** (string, optional): Human-readable description of the host

## IP Allocation Guidelines

- **Cluster 1**: Use IP range `10.10.0.10` to `10.10.0.19`
- **Cluster 2**: Use IP range `10.10.0.20` to `10.10.0.29`
- **Cluster N**: Use IP range `10.10.0.(N*10)` to `10.10.0.(N*10+9)`

This allocation scheme allows the controller to automatically determine cluster membership from IP addresses using the formula: `cluster_id = last_octet // 10`

## Usage

### Option 1: Automatic Loading (Recommended)

The controller will automatically load the configuration file for its cluster at startup:

```bash
# Controller for cluster 1 will load config/hosts_cluster1.json
ryu-manager --user-flags cluster_id=1 ryu.custom.my_simple_switch_13

# Controller for cluster 2 will load config/hosts_cluster2.json
ryu-manager --user-flags cluster_id=2 ryu.custom.my_simple_switch_13
```

### Option 2: Explicit Path

You can specify a custom configuration file path:

```bash
export HOST_CONFIG_FILE="/path/to/custom_hosts.json"
ryu-manager --user-flags cluster_id=1 ryu.custom.my_simple_switch_13
```

### Option 3: Environment Variable (Inline)

For testing or simple deployments, you can use an environment variable:

```bash
export STATIC_HOSTS="10.10.0.10=02:da:d9:38:7b:b1:9:13754232326308,10.10.0.20=ca:0b:5e:87:28:d5:2:66274971307137"
ryu-manager --user-flags cluster_id=1 ryu.custom.my_simple_switch_13
```

## Adding New Hosts

To add a new host to an existing cluster:

1. Open the appropriate `hosts_clusterN.json` file
2. Add a new entry under the `hosts` section:
   ```json
   "10.10.0.12": {
     "mac": "11:22:33:44:55:66",
     "port": 11,
     "dpid": "0x0c826821c8a4",
     "description": "New host h3"
   }
   ```
3. Restart the controller for the changes to take effect

## Finding MAC Addresses and Port Numbers

To find the MAC address and port number for a host connection:

```bash
# Show OVS ports and their MAC addresses
ovs-ofctl show br1

# Example output:
# 9(br1-h1): addr:02:da:d9:38:7b:b1
#     config:     0
#     state:      0
#     current:    10GB-FD COPPER
#     speed: 10000 Mbps now, 0 Mbps max
```

From this output:
- Port number: `9`
- Port name: `br1-h1`
- MAC address: `02:da:d9:38:7b:b1`

## Finding Datapath ID

```bash
# Show datapath ID
ovs-vsctl get bridge br1 datapath_id

# Convert to hex (if needed)
printf "0x%s\n" $(ovs-vsctl get bridge br1 datapath_id | tr -d '"')
```

## Example: Multi-Host Cluster Configuration

```json
{
  "cluster_id": 1,
  "hosts": {
    "10.10.0.10": {
      "mac": "02:da:d9:38:7b:b1",
      "port": 9,
      "dpid": "0x0c826821c8a4",
      "description": "Host h1 on OVS1"
    },
    "10.10.0.11": {
      "mac": "aa:bb:cc:dd:ee:ff",
      "port": 10,
      "dpid": "0x1234567890ab",
      "description": "Host h2 on OVS6"
    },
    "10.10.0.12": {
      "mac": "00:11:22:33:44:55",
      "port": 5,
      "dpid": "0xfedcba987654",
      "description": "Host h3 on OVS7"
    }
  }
}
```

## Notes

- The `description` field is optional and for documentation purposes only
- MAC addresses should match the OVS port hardware address, not the host's interface MAC
- In the "one host one OVS" architecture, each host typically has its own dedicated OVS switch
- Configuration files are loaded at controller startup; restart required for changes
- If a configuration file is not found, the controller will still work using reactive discovery
