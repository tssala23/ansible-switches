# Ansible Site for Managing MOC/OCT Switches
Ansible site for MOC/OCT switches

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
    admin: "up"
    mtu: 9216
```

The interface label must be in the format `STACK/PORT` or `STACK/PORT/FANOUT`

The following table has all of the available fields for interfaces

| Field Label   | Description                            | Examples                                   | Mutually Exclusive With     |
|---------------|----------------------------------------|--------------------------------------------|-----------------------------|
| description   | Description of the interface           | "Example interface"                        |                             |
| admin         | Admin state of interface               | "up" or "down"                             |                             |
| fanout        | Fanout configuration                   | "single", "dual", or "quad"                |                             |
| fanout_speed  | Fanout speed                           | In the format ##G, such as "10G"           |                             |
| untagged_vlan | VLAN to untag on this interface        | Integer value, ie. 780                     | ip4, ip6                    |
| tagged_vlans  | List of VLANs to tag on this interface | [780, 630]                                 | ip4, ip6                    |
| ip4           | IPv4 address for this interface        | 10.0.0.1/24                                | untagged_vlan, tagged_vlans |
| ip6           | IPv6 address for this interface        | 2001:0db8:85a3:0000:0000:8a2e:0370:7334/64 | untagged_vlan, tagged_vlans |
| mtu           | MTU of interface                       | 9216                                       |                             |


## Switch Configuration

Switches will need some manual configuration before being able to be set up from this ansible site.
### Dell OS9 Switches

1. On the switch, enter `conf` mode
1. Set the enable password: `enable password <DEFAULT_OS9_PASSWD>`
1. Set the ssh user `username admin password <DEFAULT_OS9_PASSWD>`
1. Enable ssh server `ip ssh server enable`
1. Set the access IP (usually `managementethernet 1/1`)
