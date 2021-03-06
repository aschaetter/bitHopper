  #!/usr/bin/python
#License#
#bitHopper by Colin Rice is licensed under a Creative Commons Attribution-NonCommercial-ShareAlike 3.0 Unported License.
#Based on a work at github.com.

import eventlet
from eventlet.green import threading, time, socket

# Global timeout for sockets in case something leaks
socket.setdefaulttimeout(900)

class Data():
    def __init__(self,bitHopper):
        self.users = {}
        self.bitHopper = bitHopper
        self.pool = self.bitHopper.pool
        self.db = self.bitHopper.db
        self.speed = self.bitHopper.speed
        self.difficulty = self.bitHopper.difficulty
        self.lock = threading.RLock()
        try:
            self.user_drop_time = self.bitHopper.config.get('main', 'user_drop_time')
        except:
            self.user_drop_time = 3600
        with self.lock:
            users = self.db.get_users()

            for user in users:
                self.users[user] = {'shares':users[user]['shares'],'rejects':users[user]['rejects'], 'last':0, 'shares_time': [], 'hash_rate': 0}
        eventlet.spawn_n(self.prune)

    def prune(self):
        while True:
            with self.lock:
                for user in self.users:
                    for share_time in self.users[user]['shares_time']:
                        if time.time() - share_time > 60 * 15:
                            if len(self.users[user]['shares_time']) > 1:
                                self.users[user]['shares_time'].remove(share_time)
                    self.users[user]['hash_rate'] = (len(self.users[user]['shares_time']) * 2**32) / (60 * 15 * 1000000)
            eventlet.sleep(30)
    
    def get_users(self):
        with self.lock:
            users = {}
            for item in self.users:
                if self.users[item]['shares'] > 0:
                    shares_time = self.users[item]['shares_time']
                    if len(shares_time) > 0 and time.time()-max(shares_time) < int(self.user_drop_time):
                        users[item] = self.users[item]
            return users

    def user_share_add(self,user,password,shares,server):
        with self.lock:
            if user not in self.users:
                self.users[user] = {'shares':0,'rejects':0, 'last':0, 'shares_time': [], 'hash_rate': 0}
            self.users[user]['last'] = int(time.time())
            self.users[user]['shares'] += shares
            self.users[user]['shares_time'].append(int(time.time()))
            self.users[user]['hash_rate'] = (len(self.users[user]['shares_time']) * 2**32) / (60 * 15 * 1000000)

    def user_reject_add(self,user,password,rejects,server):
        with self.lock:
            if user not in self.users:
                self.users[user] = {'shares':0,'rejects':0, 'last':0, 'shares_time': [], 'hash_rate': 0}
            self.users[user]['rejects'] += rejects

    def reject_callback(self,server,data,user,password):
        try:
            self.db.update_rejects(server,1, user, password)
            self.pool.get_servers()[server]['rejects'] += 1
            self.user_reject_add(user, password, 1, server)
        except Exception, e:
            self.bitHopper.log_dbg('reject_callback_error')
            self.bitHopper.log_dbg(str(e))
            return

    def data_callback(self,server,data, user, password):
        try:
            if data != []:
                self.speed.add_shares(1)
                self.db.update_shares(server, 1, user, password)
                self.pool.get_servers()[server]['user_shares'] += 1
                self.pool.get_servers()[server]['expected_payout'] += 1.0 / self.difficulty['btc'] * 50.0
                self.user_share_add(user, password, 1, server)

        except Exception, e:
            self.bitHopper.log_dbg('data_callback_error')
            self.bitHopper.log_dbg(str(e))
    
