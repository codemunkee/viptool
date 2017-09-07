#!/usr/bin/python

# I've written this as a way to more easily take machines
# in and out of the F5 VIPs we have. -russ 2014/06/03

import sys
import getopt
import ConfigParser
import pycontrol.pycontrol as pc


class vipper:

    def __init__(self):
        self.init_vars()
        self.parse_args()
        self.validate_args()

    def init_vars(self):
        viptool_conf = '/etc/somewhere/viptool.conf'
        config.read(viptool_conf)
        try:
            self.uname = config.get('viptool', 'user')
            self.upass = config.get('viptool', 'pass')
        except(ConfigParser.NoSectionError):
            print 'Unable to open config file. Either the config (%s) is not'\
                  ' there or you need to be using sudo!' % viptool_conf
            sys.exit()

        # This is the friendly Pool Name
        self.pool = None
        # This is the Pool Name the F5 Uses
        self.pname = None
        # This is the friendly Member Name
        self.member = None
        # This is the Pool Name the F5 Uses
        self.pmember = None
        self.port = None
        self.show_pool = False
        self.show_all_pools = False
        self.enable = False
        self.disable = False
        self.force = False


        self.pools = {
            ## VIP Configs
            'vip-name': {
                'port(integer)': {
                    'hosts': {
                        'host1': 'ip:port',
                        'host2': 'ip:port'
                    },
                    'f5info': {
                        'host': 'LB hostname',
                        'pname': 'LB Pool name'
                    }
                }
            },

  }

    def usage(self, msg=None):
        """Print a usage message and exit 0. If error
        message is specified, then print it and exit 1."""

        if msg is None:
            stream = sys.stdout
        else:
            stream = sys.stderr

        usage = """\n%s:

        Tool to take Servers In and Out of a VIP:

            Available Options:
            --status (Show the Current State of a VIP)
            --avail (Show the available VIPs)
            --enable (Enable VIP Member)
            --disable (Disable VIP Member)
            --force (Used with --disable, forces VIP Member offline
                     immediately, rather than waiting for connections 
                     to drop off gracefully)
            --pool (Pool Name)
            --port (Port Number of the VIP)
            --member (name of the VIP Member to be toggled)
            --help (Show this message)""" % sys.argv[0]

        stream.write("%s\n\n" % usage)
        stream.flush()

        if msg:
            stream.write("\nERROR: %s\n" % msg)
            sys.exit(1)
        else:
            sys.exit(0)


    def parse_args(self):
        """ parse command line options """
        try:

            options, rem = getopt.getopt(sys.argv[1:], 'o:v', ['help',
                                                               'status',
                                                               'avail',
                                                               'enable',
                                                               'disable',
                                                               'force',
                                                               'pool=',
                                                               'port=',
                                                               'member='])
            if not options:
                msg = 'This script requires command line options.'
                self.usage(msg)

            for opt, arg in options:
                if opt in ('-h', '--help'):
                    self.usage()
                elif opt in ('--status'):
                    self.show_pool = True
                elif opt in ('--avail'):
                    self.show_all_pools = True
                elif opt in ('--enable'):
                    self.enable = True
                elif opt in ('--disable'):
                    self.disable = True
                elif opt in ('--force'):
                    self.force = True
                elif opt in ('--pool'):
                    self.pool = arg
                elif opt in ('--port'):
                    self.port = arg
                elif opt in ('--member'):
                    self.member = arg

        except getopt.GetoptError, err:
            self.usage('%s' % err)

    def validate_args(self):
        """ validate arguments """
        if (self.enable and self.disable) or\
           (self.enable and self.show_pool) or\
           (self.disable and self.show_pool) or\
           (self.show_all_pools and self.enable) or\
           (self.show_all_pools and self.disable) or\
           (self.show_all_pools and self.show_pool):
            msg = 'The --enable, --disable, --avail, and --list options are'\
                  ' mutually exclusive.'
            self.usage(msg)
        if (self.disable or self.enable) and not self.member:
            msg = 'You must provide a member name when enabling or disabling.'
            self.usage(msg)
        if not self.pool and not self.show_all_pools:
            msg = 'You must provide a Pool Name.'
            self.usage(msg)
        if not self.port and not self.show_all_pools:
            msg = 'You must provide a Port Number.'
            self.usage(msg)
        if not self.enable and not self.disable and not self.show_pool\
            and not self.show_all_pools:
            msg = 'You must supply at least one action, --enable, --disable,'\
                  ' --avail or --list.'
            self.usage(msg)

    def validate_pool(self):
        """ Make sure the Pool exists in our Dictionary """
        try:
           self.host = self.pools[self.pool][self.port]['f5info']['host']
           self.pname = self.pools[self.pool][self.port]['f5info']['pname']
        except KeyError:
           print '\nUnable to find pool with the name "%s" on port %s.'\
                 % (self.pool, self.port)
           self.show_config_pools()
           sys.exit()

        if self.member:
            self.validate_member()

    def validate_member(self):
        """ Make sure the Pool member exists in our Dictionary """
        try:
           self.pmember = self.pools[self.pool][self.port]['hosts'][self.member]
        except KeyError:
           print '\nUnable to find pool member with the name %s.' % self.member
           print '\nI know about the following pool members:\n'
           for mem in self.pools[self.pool][self.port]['hosts']:
               print mem
           print
           sys.exit()

    def show_config_pools(self):
        """ This shows defined pools per the config """
        print '\nI know about the following pools:\n'
        for pool in sorted(self.pools):
            for port in self.pools[pool]:
                print '%s (Port %s)' % (pool, port)
        print

    def create_session(self):
        conn = pc.BIGIP(hostname=self.host,
                        username=self.uname,
                        password=self.upass,
                        fromurl=True,
                        wsdls=['LocalLB.Pool', 'LocalLB.PoolMember'])

        return conn.LocalLB.Pool, conn.LocalLB.PoolMember

    def create_memobj(self, mses, member):
        """ Create and Object for a Member of an LB Pool """
        ip,port = member.split(':')
        pmem = mses.typefactory.create('Common.IPPortDefinition')
        pmem.address = ip
        pmem.port = int(port)
        return pmem
    
    def create_stateobj(self, mses, member, objtype):
        """ Create Session or Monitor State Sequence Object. """
    
        if objtype == 'session':
            param1 = 'LocalLB.PoolMember.MemberSessionState'
            param2 = 'LocalLB.PoolMember.MemberSessionStateSequence'
        elif objtype == 'monitor':
            param1 = 'LocalLB.PoolMember.MemberMonitorState'
            param2 = 'LocalLB.PoolMember.MemberMonitorStateSequence'

        try:
            state = mses.typefactory.create(param1)
            state.member = member
            # Create State Sequence Object
            state_seq = mses.typefactory.create(param2)
            # attribute that maps to a list of 'Common.IPPortDefinition' objects.
            state_seq.item = state
            
            return state_seq

        except Exception, e:
            print e
    
    def toggle_member(self, mses, pool, sstate, mstate, enable):
        """ This will change the Status of a LB Pool Member to take
        it in or out of the VIP. """

        mstate.item.monitor_state = 'STATE_ENABLED'
        if enable:
            sstate.item.session_state = 'STATE_ENABLED'
            print 'Enabling %s on %s!' % (self.member, self.pool)
        else:
            sstate.item.session_state = 'STATE_DISABLED'
            if self.force:
                mstate.item.monitor_state = 'STATE_DISABLED'
                print 'Disabling %s on %s immediately!' % (self.member, self.pool)
            else:
                print 'Disabling %s on %s!' % (self.member, self.pool)

        try:
            mses.set_session_enabled_state(pool_names =
                    [pool], session_states = [sstate])
            mses.set_monitor_state(pool_names =
                    [pool], monitor_states = [mstate])
        except Exception, e:
            print e

    def get_hname(self, pool, port, mem):
        hname = None
        for host in self.pools[pool][port]['hosts']:
            if self.pools[pool][port]['hosts'][host] == mem:
                hname = host
        return hname

    def get_pool_status(self, ses, pool):
        """ Get Brief Status """
        status = ses.get_object_status(pool_names = [pool])
        memobjs = status[0]
        for obj in memobjs:    
            ipport = obj[0]
            stat = obj[1]
            mem = '%s:%s' % (ipport['address'], ipport['port'])
            avail = None
            if stat['availability_status'] == 'AVAILABILITY_STATUS_GREEN':
                avail = 'Online'
            else:
                avail = 'Offline'
            en = None
            if stat['enabled_status'] == 'ENABLED_STATUS_ENABLED':
                en = 'Enabled'
            else:
                en = 'Disabled'
            hname = self.get_hname(self.pool, self.port, mem)
            print '%s (%s) -> Monitor State: %s (%s)' % (hname, mem, avail, en)
            

    def main(self):
        if self.show_all_pools:
           self.show_config_pools()
        if self.show_pool:
            self.validate_pool()
            pses, mses = self.create_session()
            print '\nPool Status (%s):\n' % self.pool
            self.get_pool_status(mses, self.pname)
            sys.exit()
        if self.disable or self.enable:
            self.validate_pool()
            pses, mses = self.create_session()
            memobj = self.create_memobj(mses, self.pmember)
            # Session State Sequence Object
            sstate = self.create_stateobj(mses, memobj, 'session')
            # Monitor State Sequence Object
            mstate = self.create_stateobj(mses, memobj, 'monitor')
            if self.enable:
                self.toggle_member(mses, self.pname, sstate, mstate, True)
            if self.disable:
                self.toggle_member(mses, self.pname, sstate, mstate, False)
            sys.exit()


if __name__ == '__main__':
    config = ConfigParser.ConfigParser()
    v = vipper()
    v.main()
