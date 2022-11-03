import re
import yaml
import pathlib

def validateIntfConfig(intf_dict):
    def raiseValueError(intf_label, msg):
        raise ValueError("Interface " + intf_label + ": " + msg)

    if type(intf_dict) is not dict:
        raise ValueError("Interface configuration must be a yaml dictionary")

    # define interface label matching regex
    intf_label_rgx = re.compile("^\d+\/\d+(\/\d+)?$")
    intf_fanout_speed_rgx = re.compile("^(10|25|40|100)(g|G)")

    for intf_label,intf in intf_dict.items():
        if not re.fullmatch(intf_label_rgx, intf_label):
            raiseValueError(intf_label, "Interface label must be in the format STACK/PORT or STACK/PORT/FANOUT")

        foundL2 = False
        foundL3 = False
        for intf_field,val in intf_dict[intf_label].items():
            if intf_field == "description":
                if type(val) is not str:
                    raiseValueError(intf_label, "Description value must be a string")
                if val == "":
                    raiseValueError(intf_label, "Description must not be an empty string")

            elif intf_field == "admin":
                if type(val) is not str:
                    raiseValueError(intf_label, "Admin value must be a string")
                if val != "up" and val != "down":
                    raiseValueError(intf_label, "Admin value must be set to 'up' or 'down'")

            elif intf_field == "fanout":
                if type(val) is not str:
                    raiseValueError(intf_label, "Fanout value must be a string")
                if val != "single" and val != "dual" and val != "quad":
                    raiseValueError(intf_label, "Fanout value must be 'single', 'dual', or 'quad'")

            elif intf_field == "fanout_speed":
                if type(val) is not str:
                    raiseValueError(intf_label, "Fanout speed value must be a string")
                if not re.fullmatch(intf_fanout_speed_rgx, val):
                    raiseValueError(intf_label, "Fanout speed value must be 10g, 25g, 40g, or 100g")

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

def main():
    host_vars_dir = pathlib.Path(__file__ + "/../../host_vars").resolve()
    print(host_vars_dir)

    file_list = [f for f in host_vars_dir.glob('**/*') if f.is_file()]

    for f in file_list:
        print("Validating file " + str(f) + "...")
        # loop through each host var file
        with open(f, 'r') as file:
            yaml_import = yaml.safe_load(file)

            for key in yaml_import.keys():
                if key == "interfaces":
                    validateIntfConfig(yaml_import[key])

if __name__ == "__main__":
    main()
