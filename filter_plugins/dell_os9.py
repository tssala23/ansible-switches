def os9_getLabelMap(sw_config, reverse=False):
    label_map = {}

    # don't include these interface types in the label map
    intf_blacklist = [
        "ManagementEthernet",
        "vlan",
        "port-channel",
        "group",
        "loopback",
        "null",
        "tunnel"
    ]

    intf_conf = [ i for i in sw_config if i.startswith('interface') and not any(y in i for y in intf_blacklist) ]

    for intf in intf_conf:
        intf_parts = intf.split(" ")

        sw_label = " ".join(intf_parts[1:3])
        conf_label = intf_parts[2]

        if reverse:
            label_map[sw_label] = conf_label
        else:
            label_map[conf_label] = sw_label

    return label_map

def os9_getVLANAssignmentMap(vlan_dict, sw_config):
    # helper method which takes a dell os9 interface range as an input and outputs a list as a result of the range
    def parseRange(s):
        out = []

        s_parts = s.split(",")
        for cur in s_parts:
            if "-" in cur:
                # this is a range
                cur_parts = cur.split("-")
                first_elem_parts = cur_parts[0].split("/")
                last_elem_parts = cur_parts[1].split("/")
                part_size = len(first_elem_parts)

                index = -1
                if part_size >= 1 and first_elem_parts[0] != last_elem_parts[0]:
                    # this is unlikely
                    index = 0
                elif part_size >= 2 and first_elem_parts[1] != last_elem_parts[1]:
                    index = 1
                elif part_size >= 3 and first_elem_parts[2] != last_elem_parts[2]:
                    index = 2

                if index >= 0:
                    for x in range(first_elem_parts[index], last_elem_parts[index] + 1):
                        out_str = first_elem_parts
                        out_str[index] = x
                        out.append(out_str)
            else:
                # this is not a range
                out.append(cur)

        return out

    out = {}

    revLabelMap = os9_getLabelMap(sw_config, reverse=True)

    for vlan in vlan_dict.keys():
        intf_label = "interface vlan " + str(vlan)
        cur_vlan_dict = sw_config[intf_label]
        if conf_label not in out:
            out[conf_label] = {}
        if "untagged" not in out[conf_label]:
            out[conf_label]["untagged"] = []
        if "tagged" not in out[conf_label]:
            out[conf_label]["tagged"] = []

        for vlan_entry in cur_vlan_dict.keys():
            if vlan_entry.startswith("untagged"):
                tag_str = "untagged"
            elif vlan_entry.startswith("tagged"):
                tag_str = "tagged"
            else:
                continue

            # found untagged entry
            vlan_entry_parts = vlan_entry.split(" ")
            untag_port_type = vlan_entry_parts[1]
            untag_port_range = vlan_entry_parts[2]

            cur_portlist = parseRange(untag_port_range)

            for port in cur_portlist:
                full_swname = untag_port_type + " " + port
                conf_label = revLabelMap[full_swname]

                out[conf_label][tag_str].append(vlan)

def os9_recurseLines(index, split_conf):

    # helper method for getting the number of prefixed spaces in a given string
    def getSpacesInStartOfString(s):
        return len(s) - len(s.lstrip())

    out = {}

    trimmed_split_conf = split_conf[index:]
    numIndex = getSpacesInStartOfString(trimmed_split_conf[0])

    lastLine = ""
    skipint = 0
    for i, line in enumerate(trimmed_split_conf):
        if skipint > 0:
            skipint -= 1
            continue

        if "!" in line:
            continue

        cur_numSpaces = getSpacesInStartOfString(line)

        # remove whitespace after counting
        line = line.strip()

        if cur_numSpaces < numIndex:
            # we're done with this section
            return i - 1,out

        if cur_numSpaces == numIndex:
            # we can add this directly
            out[line] = {}

        if cur_numSpaces > numIndex:
            # start a new recursion
            rec_line = os9_recurseLines(i, trimmed_split_conf)

            out[lastLine] = rec_line[1]
            skipint = rec_line[0]  # skip the lines that were covered by the recursion

        lastLine = line
        lastIndex = i

    return lastIndex - 1,out

def os9_getFactDict(sw_facts):
    split_conf = sw_facts["ansible_facts"]["ansible_net_config"].splitlines()

    return os9_recurseLines(0, split_conf)[1]

def os9_getSwIntfName(intf_label, sw_config):
    label_map = os9_getLabelMap(sw_config)

    if intf_label not in label_map:
        return None

    return label_map[intf_label]

def os9_getFanoutConfig(intf_dict, sw_config):

    out = []

    label_map = os9_getLabelMap(sw_config)

    for intf_label,intf in intf_dict.items():

        has_fanout = "fanout" in intf and "fanout_speed" in intf
        if has_fanout:
            # get port number
            intf_parts = intf_label.split("/")
            port_num = intf_parts[1]

            # ! TODO - add checks for valid fanout/fanout_speed regex
            conf_str_start = "stack-unit 1 port " + str(port_num)
            conf_str = conf_str_start + " portmode " + intf["fanout"] + " speed " + intf["fanout_speed"] + " no-confirm"

            existing_fanout_conf = [ k for k in sw_config.keys() if k.startswith(conf_str_start) ]
            if len(existing_fanout_conf) > 1:
                raise ValueError("Found multiple stack-unit configurations on one interface, this shouldn't happen.")

            if len(existing_fanout_conf) > 0:
                # fanout config already exists, revert existing config
                if existing_fanout_conf[0] == conf_str:
                    # this config is already applied on the switch so we can skip this
                    continue
                else:
                    # we need to clear the old configuration first

                    # first, set all interfaces to default state within the stack
                    for x in [ k for k in sw_config.keys() if intf_label in k and k.startswith("interface") ]:
                        out.append("default " + x)

                    existing_revert = existing_fanout_conf[0].split("speed")[0].strip()
                    out.append("no " + existing_revert + " no-confirm")
            else:
                # if the config doesn't exist, we need to default the interface being fanned out
                port_label = os9_getSwIntfName(intf_label, sw_config)
                out.append("default interface " + port_label)

            out.append(conf_str)

    return out

def os9_getIntfConfig(intf_dict, sw_config):

    out_all = {}

    for intf_label,intf in intf_dict.items():

        out = []

        sw_label = os9_getSwIntfName(intf_label, sw_config)
        if sw_label is None:
            continue

        # determine if interface is it L2 or L3 mode
        l2_exclusive_settings = "untagged_vlan" in intf or "tagged_vlan" in intf
        l3_exclusive_settings = "ip4" in intf or "ip6" in intf or "keepalive" in intf

        if l2_exclusive_settings and l3_exclusive_settings:
            raise ValueError("Interface " + intf_label + " cannot operate in both L2 and L3 mode")

        if l2_exclusive_settings:
            # L2 mode
            out.append("no ip address")
            out.append("no ipv6 address")
            out.append("switchport")

            l2_hybrid = "untagged_vlan" in intf and "tagged_vlan" in intf
            if l2_hybrid:
                out.append("portmode hybrid")
            else:
                out.append("no portmode hybrid")
        elif l3_exclusive_settings:
            # L3 mode
            out.append("no portmode")
            out.append("no switchport")

            if "ip4" in intf:
                out.append("ip address " + intf["ip4"])
            else:
                out.append("no ip address")

            if "ip6" in intf:
                out.append("ipv6 address " + intf["ip6"])
            else:
                out.append("no ipv6 address")

        # set description
        if "description" in intf:
            if intf["description"] == "":
                raise ValueError("Interface " + intf_label + " description must not be an empty string")

            out.append("description " + intf["description"])

        # set admin state
        if "admin" in intf:
            if intf["admin"] == "up":
                out.append("no shutdown")
            elif intf["admin"] == "down":
                out.append("shutdown")

        if "mtu" in intf:
            out.append("mtu " + str(intf["mtu"]))
        else:
            out.append("no mtu")

        # additional confs
        if "additional" in intf:
            for add_conf in intf["additional"]:
                out.append(add_conf)

        if out:
            # output list is not empty
            out_all[sw_label] = out

    return out_all

def os9_getVlanConfig(intf_dict, vlan_dict, sw_config):

    out = {}

    vlanMap = os9_getVLANAssignmentMap(vlan_dict, sw_config)

    for intf_label,intf in intf_dict.items():

        existing_vlans = vlanMap[intf_label]

        sw_label = os9_getSwIntfName(intf_label, sw_config)
        if sw_label is None:
            continue

        #has_vlans = "untagged_vlan" in intf or "tagged_vlan" in intf
        #if has_vlans:
        #    out[sw_label] = []

        if "untagged_vlan" in intf:
            # has untagged vlan
            vlan = intf["untagged_vlan"]

            if vlan not in out:
                out[vlan] = []

            if vlan in existing_vlans["untagged"]:
                existing_vlans["untagged"].remove(vlan)

            out[vlan].append("untagged " + str(sw_label))

        if "tagged_vlans" in intf:
            # has untagged vlans
            for vlan in intf["tagged_vlans"]:
                if vlan not in out:
                    out[vlan] = []

                if vlan in existing_vlans["tagged"]:
                    existing_vlans["tagged"].remove(vlan)

                out[vlan].append("tagged " + str(sw_label))

        # remove any old vlans no longer in config
        for untg_vlan in existing_vlans["untagged"]:
            out[untg_vlan].append("no untagged " + str(sw_label))
        for tg_vlan in existing_vlans["tagged"]:
            out[tg_vlan].append("no tagged " + str(sw_label))

    return out

class FilterModule(object):
    def filters(self):
        return {
            "os9_getFactDict": os9_getFactDict,
            "os9_getFanoutConfig": os9_getFanoutConfig,
            "os9_getIntfConfig": os9_getIntfConfig,
            "os9_getVlanConfig": os9_getVlanConfig
        }
