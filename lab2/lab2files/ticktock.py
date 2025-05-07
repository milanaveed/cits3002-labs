# from defs import Event


# # This is a simple protocol source file which demonstrates the use of timer
# # events (though it's not really a protocol).


# # The following variables and functions will all be injected by the simulator.
# #
# # Importantly, nodeinfo and linkinfo always reflect information about the
# # currently executing node.

# nodeinfo = None
# linkinfo = []

# def start_timer(event, usecs, data = None):
#   return 0 # returns a timerid

# def set_handler(event, callback):
#   pass


# # Everything below here is our protocol-specific code.


# # The Node class, which must be provided to make the simulator happy. Each node
# # (i.e. computer) in the network topology is represented by an instance of Node.
# #
# class Node:
#   def __init__(self):
#     self.which = 0


#   def timeouts(self):
#     self.which = self.which + 1
#     print('{}\t{}'.format(self.which, 'tick' if self.which % 2 == 0 else '\ttock'))
    
#     # reschedule Event.TIMER1 to occur again in 1 second
#     start_timer(Event.TIMER1, 1000000)


#   def reboot_node(self):
#     # indicate that we are interested in the Event.TIMER1 event
#     set_handler(Event.TIMER1, self.timeouts)

#     # request that Event.TIMER1 occur in 1 second
#     start_timer(Event.TIMER1, 1000000)



from defs import Event

# This is a simple protocol source file that demonstrates the use of timer
# events. It is not an actual protocol but serves as an example of handling
# periodic events using a timer.

# The following variables and functions will be injected by the simulator.
# These allow interaction with the network simulation environment.

# `nodeinfo` contains information about the currently executing node.
nodeinfo = None

# `linkinfo` contains details about network links associated with the node.
linkinfo = []


def start_timer(event, usecs, data=None):
    """
    Starts a timer for a given event, scheduling it to occur after the specified time.
    
    Parameters:
        event (Event): The event type to be triggered.
        usecs (int): Time in microseconds after which the event will be triggered.
        data (optional): Additional data to be passed when the event occurs.
    
    Returns:
        int: A timer ID (placeholder, as this function is simulated).
    """
    return 0  # Returns a simulated timer ID


def set_handler(event, callback):
    """
    Registers a callback function to be executed when the specified event occurs.
    
    Parameters:
        event (Event): The event type to register the handler for.
        callback (function): The function to be called when the event occurs.
    """
    pass  # Placeholder function, handled by the simulator


# The Node class represents a node (computer) in the network simulation.
# Each instance of Node corresponds to a single network node in the topology.
class Node:
    def __init__(self):
        """
        Initializes the Node instance.
        
        Attributes:
            which (int): Counter used to alternate between "tick" and "tock" messages.
        """
        self.which = 0

    def timeouts(self):
        """
        Handles timer events and prints alternating "tick" and "tock" messages.
        This function is triggered each time Event.TIMER1 occurs.
        """
        self.which = self.which + 1  # Increment the counter
        print('{}\t{}'.format(self.which, 'tick' if self.which % 2 == 0 else '\ttock'))
        
        # Reschedule Event.TIMER1 to occur again in 1 second (1,000,000 microseconds)
        start_timer(Event.TIMER1, 1000000)

    def reboot_node(self):
        """
        Initializes the node by setting up a handler for Event.TIMER1.
        This function is called when the node starts or reboots.
        """
        # Register the timeouts() method as the handler for Event.TIMER1
        set_handler(Event.TIMER1, self.timeouts)

        # Request Event.TIMER1 to occur after 1 second (1,000,000 microseconds)
        start_timer(Event.TIMER1, 1000000)
