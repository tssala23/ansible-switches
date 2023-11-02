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
  twentyFiveGigE 1/1:
    description: "example interface"
    state: "up"
    mtu: 9216
  Port-channel 1:
    state: "up"
    lag-members:
      - "hundredGigE 1/1"
      - "hundredGigE 1/2"
    portmode: "access"
    untagged: 10
  Vlan 207:
    state: "up"
    ip4: "10.10.10.10/20"
```

### Available Fields

* `name` Only for VLANs, sets the name of interfaces. (String)
* `description` Sets the description of the interface. (String)
* `state` Sets the admin state of the mode ("up", or "down")
* `mtu` Sets the MTU of the interface (Integer 576-9416)
* `fec` If false, forward-error-correction is disabled on the interface (Boolean)
* `autoneg` If false, auto-negotiation is disabled on the interface (Boolean)
* `stp-edge` Sets the port as an edge-port for STP (Boolean)
* `managed` If true, this interface will not be configured by ansible. Works for both VLANs and interfaces (Boolean)
* `portmode` L2 portmode of an interface (String "access", "trunk", or "hybrid")
* `untagged` Single vlan to untag, requires portmode access or hybrid (Integer 2-4094)
* `tagged` List of vlans to tag, requires portmode trunk or hybrid (List of Integers 2-4094)
* `ip4` Sets the IPv4 address of the interface (String "X.X.X.X/YY")
* `ip6` Sets the IPv6 address of the interface (String)
* `lag-members` List of non-LACP lag members for a port channel (List of Strings, interface names)
* `lacp-members-active` List of LACP active members for a port channel (List of Strings, interface names)
* `lacp-members-passive` List of LACP passive members for a port channel (List of Strings, interface names)
* `lacp-rate` Sets the switch rate for LACP only (String "fast" or "slow")
* `mlag` Set the label of the peer port-channel for a paired switch (String interface name)

## Switch Configuration

Switches will need some manual configuration before being able to be set up from this ansible site.

### Dell OS9 Switches

1. On the switch, enter `conf` mode
1. Set the enable password: `enable password <DEFAULT_OS9_PASSWD>`
1. Set the ssh user `username admin password <DEFAULT_OS9_PASSWD>`
1. Enable ssh server `ip ssh server enable`
1. Set the access IP (usually `managementethernet 1/1`)

## Future Improvements

* Validation scripts that don't require access to switches
* Case-insensitive matching for interface labels
* VLAN groups to be defined in tagged/untagged sections
* Switch system configuration (STP, etc.)
* Add "speed" field for some interfaces
* Ability to map connections between devices
