#! /usr/bin/env python

# http://www.wiredfool.com/2009/02/01/remote-growl-notifications/
# http://the.taoofmac.com/space/Projects/netgrowl
# http://dbus.freedesktop.org/doc/dbus-python/doc/tutorial.html
# http://developer.pidgin.im/wiki/DbusHowto

# for maintaining multiple threads
import threading
from time import sleep

# for growling an event
from socket import AF_INET, SOCK_DGRAM, SOCK_STREAM, socket
import netgrowl

# for listening to pidgin through dbus
import dbus, gobject
from dbus.mainloop.glib import DBusGMainLoop

import re

def strip_tags(value):
    "Return the given HTML with all tags stripped."
    return re.sub(r'<[^>]*?>', '', value) 

class DbusMonitor(threading.Thread):
    def __init__(self, proxy_client_event = None):
        # call parent constructor
        threading.Thread.__init__(self)

        # recreate a semaphore around each of the socket writes
        self.s_sem = threading.Semaphore()

        # start the local growl proxy port and test connection to remote proxy
        self.initProxyClient(proxy_client_event)

        # init dbus and register pidgin callbacks
        self.initDbus()
        self.initPidginDbusHooks()

    def sendGrowl(self, **kwargs):
        kwargs.setdefault("application", "finch")
        kwargs.setdefault("password", "quesse")
        kwargs.setdefault("title", "finch")

        print "sending Growl(title='%s', msg='%s')" % (kwargs["title"],
                                                       kwargs["description"])

        p = netgrowl.GrowlNotificationPacket(**kwargs)
        self.s_sem.acquire()
        self.s.sendto(p.payload(), self.addr)
        self.s_sem.release()

    def initProxyClient(self, proxy_client_event = None):
        # initialize the udp socket to write growl messages to
        # this destination of the first hop should point to the proxy client
        self.addr = ("localhost", netgrowl.GROWL_UDP_PORT)
        self.s = socket(AF_INET, SOCK_DGRAM)

        # then there is another thread that is a GrowlProxyClient
        # we're going to wait until it starts before sending the registration packet
        if(proxy_client_event is not None):
            print "DbusMonitor: waiting to send Registration packet"
            proxy_client_event.wait()

        print "DbusMonitor: sending the Registration packet"
        p = netgrowl.GrowlRegistrationPacket(application="finch",
                                             password="quesse")
        p.addNotification()
        self.s.sendto(p.payload(), self.addr)

        # send an introductory message
        self.sendGrowl(title="DbusMonitor",
                       description="Successfully connected")

    def initDbus(self):
        # initialize the dbus loop
        self.dbus_loop = DBusGMainLoop(set_as_default=True)
        self.session_bus = dbus.SessionBus()

    def initPidginDbusHooks(self):
        self.purple = dbus.Interface(
            self.session_bus.get_object("im.pidgin.purple.PurpleService",
                                        "/im/pidgin/purple/PurpleObject"),
            "im.pidgin.purple.PurpleInterface")

        # register the callbacks
        self.session_bus.add_signal_receiver(
            self.pidgin_received_im_msg_cb,
            dbus_interface="im.pidgin.purple.PurpleInterface",
            signal_name="ReceivedImMsg")

        self.session_bus.add_signal_receiver(
            self.pidgin_received_chat_msg_cb,
            dbus_interface="im.pidgin.purple.PurpleInterface",
            signal_name="ReceivedChatMsg")

        self.session_bus.add_signal_receiver(
            self.pidgin_received_conversation_created_cb,
            dbus_interface="im.pidgin.purple.PurpleInterface",
            signal_name="ConversationCreated")

        self.session_bus.add_signal_receiver(
            self.pidgin_buddy_signed_on_cb,
            dbus_interface="im.pidgin.purple.PurpleInterface",
            signal_name="BuddySignedOn")

        self.session_bus.add_signal_receiver(
            self.pidgin_buddy_signed_off_cb,
            dbus_interface="im.pidgin.purple.PurpleInterface",
            signal_name="BuddySignedOff")

        self.session_bus.add_signal_receiver(
            self.pidgin_buddy_status_changed_cb,
            dbus_interface="im.pidgin.purple.PurpleInterface",
            signal_name="BuddyStatusChanged")

#  conversation = 98103
#  account = purple.PurpleConversationGetAccount(conversation)
#  print "account %s" % account
#  print "account protocol %s" % purple.PurpleAccountGetProtocolName(account)
#  print "account username %s" % purple.PurpleAccountGetUsername(account)
#  print "title %s" % purple.PurpleConversationGetTitle(conversation)
#  print "name %s" % purple.PurpleConversationGetName(conversation)

    def pidgin_received_im_msg_cb(self, account, sender, message, conversation, flags):
        #print "%s said: %s" % (sender, message)

        convtitle = self.purple.PurpleConversationGetTitle(conversation)
        protoname = self.purple.PurpleAccountGetProtocolName(account)
        #if protoname != "AIM" or convtitle == "deaeula":
        #    # don't show the text
        #    title = "%s: %s" % (self.purple.PurpleAccountGetProtocolName(account),
        #                        self.purple.PurpleAccountGetUsername(account))
        #    msg = "%s sent a message" % (self.purple.PurpleConversationGetTitle(conversation))
        #else:
        #    # show the text
        #    title = "%s (%s: %s)" % (self.purple.PurpleConversationGetTitle(conversation),
        #                             self.purple.PurpleAccountGetProtocolName(account),
        #                             self.purple.PurpleAccountGetUsername(account))
        #    msg = message
        title = "%s (%s: %s)" % (self.purple.PurpleConversationGetTitle(conversation),
                                 self.purple.PurpleAccountGetProtocolName(account),
                                 self.purple.PurpleAccountGetUsername(account))
        msg = strip_tags(message)

        self.sendGrowl(title=title,
                       description=msg)

    def pidgin_received_chat_msg_cb(self, account, sender, message, conversation, flags):
        #print "%s said: %s" % (sender, message)

        # sender is just the username of the thing
        buddy = self.purple.PurpleFindBuddy(account, sender)
        title = "%s said in %s (%s: %s)" % (self.purple.PurpleBuddyGetAlias(buddy),
                                            self.purple.PurpleConversationGetTitle(conversation),
                                            self.purple.PurpleAccountGetProtocolName(account),
                                            self.purple.PurpleAccountGetUsername(account))
        msg = strip_tags(message)

        self.sendGrowl(title=title,
                       description=msg)

    def pidgin_received_conversation_created_cb(self, conversation):
        #print ("started conversation with title '%s' and name '%s'" %
        #       (self.purple.PurpleConversationGetTitle(conversation),
        #        self.purple.PurpleConversationGetName(conversation)))

        account = self.purple.PurpleConversationGetAccount(conversation)
        title = "%s: %s (sticky)" % (self.purple.PurpleAccountGetProtocolName(account),
                            self.purple.PurpleAccountGetUsername(account))
        msg = "%s started a new conversation" % (self.purple.PurpleConversationGetTitle(conversation))
        self.sendGrowl(title=title,
                       description=msg,
                       sticky=True)

    def pidgin_buddy_signed_on_cb(self, buddy):
        account = self.purple.PurpleBuddyGetAccount(buddy)
        title = "%s: %s" % (self.purple.PurpleAccountGetProtocolName(account),
                            self.purple.PurpleAccountGetUsername(account))
        msg = "%s has signed on" % (self.purple.PurpleBuddyGetAlias(buddy))

        self.sendGrowl(title=title,
                       description=msg)

    def pidgin_buddy_signed_off_cb(self, buddy):
        account = self.purple.PurpleBuddyGetAccount(buddy)
        title = "%s: %s" % (self.purple.PurpleAccountGetProtocolName(account),
                            self.purple.PurpleAccountGetUsername(account))
        msg = "%s has signed off" % (self.purple.PurpleBuddyGetAlias(buddy))

        self.sendGrowl(title=title,
                       description=msg)

    def pidgin_buddy_status_changed_cb(self, buddy, old_status, new_status):
        #print ("buddy_status_changed: buddy '%s', old_status '%s', new_status'%d'" %
        #       (buddy, old_status, new_status))

        account = self.purple.PurpleBuddyGetAccount(buddy)
        title = "%s: %s" % (self.purple.PurpleAccountGetProtocolName(account),
                            self.purple.PurpleAccountGetUsername(account))

        was_online = self.purple.PurpleStatusIsOnline(old_status)
        is_online = self.purple.PurpleStatusIsOnline(new_status)
        alias = self.purple.PurpleBuddyGetAlias(buddy)

        msg = ""

        if was_online is True and is_online is False:
            msg = "%s has signed off" % (alias)
        elif was_online is False and is_online is True:
            msg = "%s has signed on" % (alias)

        #print ("title '%s', was_online '%s', is_online '%s', alias '%s', msg '%s'" %
        #       (title, was_online, is_online, alias, msg))

        if msg is not "":
            self.sendGrowl(title=title,
                           description=msg)

    def run(self):
        loop = gobject.MainLoop()

        try:
            loop.run()
        except KeyboardInterrupt:
            print "quitting"
            loop.quit()

if __name__ == "__main__":
    d = DbusMonitor()
    d.run()
