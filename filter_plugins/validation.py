import re

def validateIntfConfig(intf_dict, vlanintf_dict):
    def raiseValueError(intf_label, msg):
        raise ValueError("Interface " + intf_label + ": " + msg)

    if type(intf_dict) is not dict:
        raise ValueError("Interface configuration must be a yaml dictionary")

    # define interface label matching regex
    intf_label_rgx = re.compile("^\d+\/\d+\/?\d+$")

    for intf_label,intf in intf_dict.items():
        if not re.fullmatch(intf_label_rgx, intf_label):
            raiseValueError(intf_label, "Interface label must be in the format STACK/PORT or STACK/PORT/FANOUT")

        foundL2 = False
        foundL3 = False
        for intf_field,val in intf_dict.items():
            if intf_field == "description":
                if type(val) is not str:
                    raiseValueError(intf_label, "Description value must be a string")

            elif intf_field == "admin":
                if type(val) is not str:
                    raiseValueError(intf_label, "Admin value must be a string")
                if val != "up" or val != "down":
                    raiseValueError(intf_label, "Admin value must be set to 'up' or 'down'")

            elif intf_field == "fanout":
                if type(val) is not str:
                    raiseValueError(intf_label, "Fanout value must be a string")
                if val != "single" or val != "dual" or val != "quad":
                    raiseValueError(intf_label, "Fanout value must be 'single', 'dual', or 'quad'")

            elif intf_field == "fanout_speed":
                if type(val) is not str:
                    raiseValueError(intf_label, "Fanout speed value must be a string")
                # ! TODO regex for validating this field

            elif intf_field == "untagged_vlan":
                if foundL3:
                    raiseValueError(intf_label, "Cannot have both L2 and L3 fields")
                if type(val) is not int:
                    raiseValueError(intf_label, "Untagged VLAN must be an integer")
                if val <= 0:
                    raiseValueError(intf_label, "Untagged VLAN must be greater than 0")

                foundL2 = True

            elif intf_field == "tagged_vlan":
                if foundL3:
                    raiseValueError(intf_label, "Cannot have both L2 and L3 fields")
                if type(val) is not list:
                    raiseValueError(intf_label, "Tagged VLANs must be a list")
                for vlan in val:
                    if type(vlan) is not int:
                        raiseValueError(intf_label, "Tagged VLANs must be integers")
                    if vlan <= 0:
                        raiseValueError(intf_label, "Tagged VLANs must be integers")

                foundL2 = True

            elif intf_field == "ip4":
                if foundL2:
                    raiseValueError(intf_label, "Cannot have both L2 and L3 fields")

                foundL3 = True

            elif intf_field == "ip6":
                if foundL2:
                    raiseValueError(intf_label, "Cannot have both L2 and L3 fields")

                foundL3 = True

            elif intf_field == "mtu":
                if type(val) is not int:
                    raiseValueError(intf_label, "MTU must be an integer")
                if val <= 0:
                    raiseValueError(intf_label, "MTU must be greater than 0")
