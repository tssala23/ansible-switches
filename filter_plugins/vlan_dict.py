def get_vlan_dict(vlan_dict, group_names):
    out = {}

    for key in vlan_dict.keys():
        # check hostnames
        enabled_hosts = vlan_dict[key]["switches"]

        for group in enabled_hosts:
            if group in group_names:
                # this host should have this vlan
                out[key] = vlan_dict[key]
    
    return out

class FilterModule(object):
    def filters(self):
        return { 'get_vlan_dict': get_vlan_dict }