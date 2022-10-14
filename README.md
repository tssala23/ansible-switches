# ansible-switches
Ansible site for MOC/OCT switches

## Site Setup

1. Install newest version of ansible
1. Install required PyPI packages:
    1. `pip install --user ansible-pylibssh`
1. Install the required ansible modules:
    1. `ansible-galaxy collection install dellemc.os9`
1. Create a file `.vault_pass` in the root location of the repo with the password to the ansible vault

## Initial Switch Setup

There is some manual setup that has to happen to a new switch to enable it to be reachable by ansible

### Dell OS9

1. On the switch, enter `conf` mode
1. Set the enable password: `enable password <DEFAULT_OS9_PASSWD>`
1. Set the ssh user `username admin password <DEFAULT_OS9_PASSWD>`
1. Enable ssh server `ip ssh server enable`
1. Set the access IP (usually `managementethernet 1/1`)