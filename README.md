# Ansible Site for Managing MOC/OCT Switches
Ansible site for MOC/OCT switches

## Supported Switch OSes

* Dell OS9 (FTOS9)

## Site Setup

1. Install newest version of ansible
1. Install required PyPI packages:
    1. `pip install --user ansible-pylibssh`
1. Install the required ansible modules: `ansible-galaxy collection install -r requirements.yaml`
1. Set up AWS CLI and be sure you can access the correct secrets
1. On your client, you may have to enable legacy kex algorithms for some switches:
    ```
    KexAlgorithms +diffie-hellman-group1-sha1,diffie-hellman-group14-sha1
    ```

## Configuration

### Interfaces

Interfaces are configured in the file `host_vars/HOST/interfaces.yaml`

An example of this file is below:

```
interfaces:
  1/1:
    description: "example interface"
    state: "up"
    mtu: 9216
```

The interface label must be in the format `STACK/PORT` or `STACK/PORT/FANOUT`

The following tables list all available fields for interface configuration. L2 configurations are mutually exclusive with L3 configurations.

#### General Fields

| Field Label | Description                    | Possible Values           |
| ----------- | ------------------------------ | ------------------------- |
| description | Description of the interface   | Any string                |
| state       | Admin state of interface       | "up" or "down"            |
| mtu         | MTU of interface               | Integer with range 1-9216 |
| edge-port   | Set port as STP edge-port      | True / False              |
| managed     | Port is managed (conf ignored) | "yes", "no", or "vlans"   |

#### Fanout Fields

If you enable fanout on a port, **none** of the other fields can be used. Instead, make subport configurations.

Example:

```
fanout: {
  type: "quad",
  speed: "10G"
}
```

#### L2 Fields

| Field Label | Description                            | Possible Values                                                          |
| ----------- | -------------------------------------- | ------------------------------------------------------------------------ |
| untagged    | VLAN to untag on this interface        | Integer with range 1-4095                                                |
| tagged      | List of VLANs to tag on this interface | List of integers with range 1-4095, or "all" for all VLANs on the switch |  |
| portmode    | L2 mode of the port                    | "access", "trunk", or "hybrid"                                           |

#### L3 Fields

| Field Label | Description                     | Possible Values                     |
| ----------- | ------------------------------- | ----------------------------------- |
| ip4         | IPv4 address for this interface | [IP]/[Prefix] IPv4 formatted string |
| ip6         | IPv6 address for this interface | [IP]/[Prefix] IPv6 formatted string |

### VLAN Interfaces

Example configuration which adds a vlan interface for vlan `100` with an ipv4 address `10.0.80.3/20`:

```
vlan_interfaces:
  100:
    ip4: "10.0.80.3/20"
```

All fields in interface configuration except L2 fields are available

### Port Channel Interfaces

Example configuration which adds a port channel `79` with a description, in lacp mode, with interface `1/1` and `1/2` part of it:

```
port_channels:
  79:
    description: "example port channel"
    mode: "lacp"
    interfaces: ["1/2", "1/1"]
```

All fields in interface configuration are available, with the following additional fields:

| Field Label          | Description                    | Possible Values                          |
| -------------------- | ------------------------------ | ---------------------------------------- |
| lag-members          | Interfaces in normal LAG       | List of interfaces                       |
| lacp-members-active  | LACP members in active config  | List of interfaces                       |
| lacp-members-passive | LACP members in passive config | List of interfaces                       |
| lacp-rate            | Set LACP rate to fast or slow  | "fast" or "slow"                         |
| mlag                 | Define mlag peer               | Interface of port channel on peer switch |

### VLANs

VLANs are defined in the `group_vars/all/vlans.yaml` file. An example of this file is below:

```
vlans:
  100:
    name: "VLAN 100"
    description: "This is the description of example vlan 100"
  101:
    name: "VLAN 101"
    description: "This is the description of example vlan 101"
  102:
    name: "VLAN 102"
    description: "hello world"
```

The following fields are available for each VLAN:

| Field Label | Description         | Possible Values |
| ----------- | ------------------- | --------------- |
| name        | Name of VLAN        | Short string    |
| description | Description of VLAN | Any string      |
| managed     | Managed VLAN        | "yes" or "no"   |

## Switch Configuration

Switches will need some manual configuration before being able to be set up from this ansible site.
### Dell OS9 Switches

1. On the switch, enter `conf` mode
1. Set the enable password: `enable password <DEFAULT_OS9_PASSWD>`
1. Set the ssh user `username admin password <DEFAULT_OS9_PASSWD>`
1. Enable ssh server `ip ssh server enable`
1. Set the access IP (usually `managementethernet 1/1`)

## Future Improvements

* Case-insensitive matching for interface labels
* VLAN groups to be defined in tagged/untagged sections
* Switch system configuration (STP, etc.)
* Add "speed" field for some interfaces
* Ability to map connections between devices