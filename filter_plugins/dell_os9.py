def getSpacesInStartOfString(s):
    return len(s) - len(s.lstrip())

def os9_getLabelMap(sw_config):
    label_map = {}

    intf_conf = [ i for i in sw_config if i.startswith('interface') ]
    intf_conf = [ x for x in intf_conf if "ManagementEthernet" not in x ]

    for intf in intf_conf:
        intf_parts = intf.split(" ")
        label_map[intf_parts[2]] = " ".join(intf_parts[1:3])

    return label_map

def os9_recurseLines(index, split_conf):
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

    for intf_label,intf in intf_dict.items():

        has_fanout = "fanout" in intf and "fanout_speed" in intf
        if has_fanout:
            # get port number
            intf_parts = intf_label.split("/")
            port_num = intf_parts[1]

            # ! TODO - add checks for valid fanout/fanout_speed regex
            conf_str_start = "stack-unit 1 port " + str(port_num)
            conf_str = conf_str_start + " portmode " + intf["fanout"] + " speed " + intf["fanout_speed"]

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
                    out.append("no " + existing_fanout_conf[0])
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
                out.append("no portmode")
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

        # additional confs
        if "additional" in intf:
            for add_conf in intf["additional"]:
                out.append(add_conf)

        if out:
            # output list is not empty
            out_all[sw_label] = out

    return out_all

def os9_getVlanConfig(intf_dict, sw_config):

    out = {}

    for intf_label,intf in intf_dict.items():

        sw_label = os9_getSwIntfName(intf_label, sw_config)
        if sw_label is None:
            continue

        has_vlans = "untagged_vlan" in intf or "tagged_vlan" in intf
        if has_vlans:
            out[sw_label] = []

        if "untagged_vlan" in intf:
            # has untagged vlan
            vlan = intf["untagged_vlan"]

            if vlan not in out:
                out[vlan] = []

            out[vlan].append("untagged " + str(sw_label))

        if "tagged_vlans" in intf:
            # has untagged vlans
            for vlan in intf["tagged_vlans"]:
                if vlan not in out:
                    out[vlan] = []

                out[vlan].append("tagged " + str(sw_label))

    return out

class FilterModule(object):
    def filters(self):
        return {
            "os9_getFactDict": os9_getFactDict,
            "os9_getFanoutConfig": os9_getFanoutConfig,
            "os9_getIntfConfig": os9_getIntfConfig,
            "os9_getVlanConfig": os9_getVlanConfig
        }
