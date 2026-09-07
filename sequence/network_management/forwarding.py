"""Forwarding protocol and forwarding message.

This module defines the `ForwardingProtocol` and `ForwardingMessage` classes.
"""
from __future__ import annotations
from typing import TYPE_CHECKING



if TYPE_CHECKING:
    from ..topology.node import QuantumRouter

from enum import Enum, auto
from ..protocol import StackProtocol
from ..message import Message
from ..utils import log

class ForwardingMessageType(Enum):
    OUTBOUND = auto()


class ForwardingMessage(Message):
    """Message used for communications between forwarding protocol instances.

    Attributes:
        msg_type (Enum): type of message, required by base `Message` class.
        receiver (str): name of destination protocol instance.
        payload (Message): message to be delivered to destination.
    """

    def __init__(self, msg_type: Enum, receiver: str, payload: Message):
        super().__init__(msg_type, receiver)
        self.payload = payload

    def __str__(self):
        return f"type={self.msg_type}, receiver={self.receiver}, payload={self.payload}"


class ForwardingProtocol(StackProtocol):
    """Class to forward messages based on the forwarding table (from the `NetworkManager`) in the routing protocol.

    Attributes:
        owner (Node): node that protocol instance is attached to.
        name (str): label for protocol instance.
    """

    def __init__(self, owner: QuantumRouter, name: str):
        """Constructor for forwarding protocol.

        Args:
            owner (Node): node protocol is attached to.
            name (str): name of protocol instance.
        """
        super().__init__(owner, name)
        self.owner: QuantumRouter = owner

    @property
    def forwarding_table(self) -> dict[str, str]:
        """Returns the forwarding table."""
        return self.owner.network_manager.get_forwarding_table()  # ty:ignore[unresolved-attribute]

    def received_message(self, src: str, msg: Message):
        """Method to directly receive messages from a node (should not be used)."""

        raise Exception("Forwarding protocol should not call this function")

    def init(self):
        pass

    def push(self, dst: str, msg: Message, next_hop: str | None = None):
        """Method to receive a message from upper protocols.

        Routing packages the message and forwards it to the next node
        based on the topology.
        """

       

        forwarding_table = self.forwarding_table
        print("Table      :", forwarding_table)
        print("Message    :", msg)

        assert dst != self.owner.name

        new_msg = ForwardingMessage(
            ForwardingMessageType.OUTBOUND,
            self.name,
            msg
        )

        # If destination is provided, calculate the next hop
        # using the routing protocol.
        if dst:

            routing_protocol = self.owner.network_manager.get_routing_protocol()

            next_hop = routing_protocol.next_hop(dst)

            print("\n===== TOPOLOGY ROUTING =====")
            print("Routing Protocol :", type(routing_protocol).__name__)
            print("Current Node     :", self.owner.name)
            print("Destination      :", dst)
            print("Next Hop         :", next_hop)
            print("============================")

            if next_hop:
                print(
                    f"Forwarding {self.owner.name} -> {next_hop}"
                )

                self._push(
                    dst=next_hop,
                    msg=new_msg
                )

            else:
                log.logger.error(
                    f"No path from {self.owner.name} to {dst}"
                )

        # If next_hop was directly provided
        elif next_hop:

            print(
                f"Forwarding {self.owner.name} -> {next_hop}"
            )

            self._push(
                dst=next_hop,
                msg=new_msg
            )

        else:
            raise Exception(
                "Both dst and next_hop are None!"
            )

    def pop(self, src: str, msg: ForwardingMessage):

        print("\n===== FORWARDING POP =====")
        print("Current node :", self.owner.name)
        print("From         :", src)

        destination = msg.payload.reservation.responder

        print("Destination  :", destination)

        # FINAL DESTINATION
        if self.owner.name == destination:

            print(
                f"===== FINAL DESTINATION: {self.owner.name} ====="
            )

            self._pop(
                src=src,
                msg=msg.payload
            )

            return

        # RELAY NODE
        print(
            f"===== RELAY NODE: {self.owner.name} ====="
        )

        # Let RSVP process this request first.
        self._pop(
            src=src,
            msg=msg.payload
        )