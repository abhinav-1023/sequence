""" TeleportApp Module
This module implements the TeleportApp class, which is responsible for managing quantum teleportation
between quantum nodes. It utilizes the TeleportProtocol to handle the teleportation process,
including the reservation of entangled pairs and the application of corrections based on classical messages.
"""
from __future__ import annotations
from .request_app import RequestApp
from ..utils import log
from ..entanglement_management.teleportation import TeleportMsgType, TeleportProtocol, TeleportMessage
from ..resource_management.memory_manager import MemoryInfo
from ..kernel.process import Process
from ..kernel.event import Event
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..topology.node import DQCNode

class TeleportApp(RequestApp):
    """Code for the teleport application.

    TeleportApp is a specialized RequestApp that implements quantum teleportation.
    It handles the teleportation protocol between two quantum nodes (Alice and Bob).

    Attributes:
        node (DQCNode): The quantum node this app is attached to.
        name (str): The name of the teleport application.
        results (list): A list of results of (timestamp, teleported_state)
        teleport_protocols (list[TeleportProtocol]): A list of teleportation protocol instances.
    """
    def __init__(self, node: DQCNode):
       
        super().__init__(node)

        self.name = f"{self.node.name}.TeleportApp"
        node.teleport_app = self

        self.results = []
        self.teleport_protocols = []

        # HH routing information
        self.hh_path = None
        self.hh_index = None
        self.hh_active = False
        log.logger.debug(f"{self.name}: initialized")

        # TWH routing information
        self.twh_path = None
        self.twh_reverse_path = None
        self.twh_active = False
        self.twh_role = None
        self.twh_index = None

        self.twh_preparation = False
        self.twh_prepared = False
        self.twh_prepared_count = 0
        self.twh_total_links = 0
        self.twh_preparation_protocols = []
        self.twh_preparation_map = {}
        self.twh_root_app = None

    def start(self, responder: str, start_t: int, end_t: int, memory_size: int, fidelity: float, data_memory_index: int):
        """Start the teleportation process.

        NOTE: only teleport one data memory qubit

        Args: 
            responder (str): Name of the responder node (Bob).
            start_t (int): Start time of the teleportation (in ps).
            end_t (int): End time of the teleportation (in ps).
            memory_size (int): Size of the memory used for the teleportation.
            fidelity (float): Target fidelity of the teleportation.
            data_memory_index (int): Index of the data qubit to be teleported.
        """
        log.logger.debug(f"{self.name}: start() -> responder={responder}, data_memory_index={data_memory_index}")

        # reserve and generate EPR pair
        super().start(responder, start_t, end_t, memory_size, fidelity)

        # init a new teleportation protocol for Alice only, and append to the list
        teleport_protocol = TeleportProtocol(self.node, alice=True, data_memory_index=data_memory_index, remote_node_name=responder)
        self.teleport_protocols.append(teleport_protocol)

    def start_hop_by_hop(
        self,
        path,
        start_t,
        end_t,
        memory_size,
        fidelity,
        data_memory_index
    ):
        self.hh_path = path
        self.hh_index = 0
        self.hh_active = True

        # Initialize HH state on every node in the route
        for index, node_name in enumerate(path):
            node = self.node.timeline.get_entity_by_name(node_name)
            app = node.teleport_app


            app.hh_path = path
            app.hh_index = index
            app.hh_active = True

        self._start_next_hop(
            start_t=start_t,
            end_t=end_t,
            memory_size=memory_size,
            fidelity=fidelity,
            data_memory_index=data_memory_index,
            source_comm_memory=None
        )

    def start_two_way_hop_by_hop(
        self,
        path,
        start_t,
        end_t,
        memory_size,
        fidelity,
        data_memory_index
    ):
        """
        Generic Two-Way Hop-by-Hop (TWH).

        Preparation:
            Source side and destination side prepare EPR links
            independently toward the middle node.

        Data:
            After all preparation links are ready, the data qubit
            travels only from source to destination.
        """

        if path is None or len(path) < 2:
            return

        self.twh_path = list(path)
        self.twh_reverse_path = list(reversed(path))
        self.twh_active = True

        middle_index = len(path) // 2

        # ------------------------------------------------------------
        # Reset TWH preparation state
        # ------------------------------------------------------------
        self.twh_preparation = True
        self.twh_prepared = False
        self.twh_prepared_count = 0
        self.twh_preparation_protocols = []

        # ------------------------------------------------------------
        # Initialize TWH state on every node
        # ------------------------------------------------------------
        for index, node_name in enumerate(path):

            node = self.node.timeline.get_entity_by_name(node_name)
            app = node.teleport_app
            app.twh_root_app = self

            app.twh_path = list(path)
            app.twh_reverse_path = list(reversed(path))
            app.twh_index = index
            app.twh_active = True

            if index < middle_index:
                app.twh_role = "SOURCE"
            elif index == middle_index:
                app.twh_role = "MIDDLE"
            else:
                app.twh_role = "DESTINATION"

            app.twh_preparation = True
            app.twh_prepared = False
            app.twh_prepared_count = 0
            app.twh_total_links = 0
            app.twh_preparation_protocols = []

        # ------------------------------------------------------------
        # Build preparation links GENERICALLY
        #
        # Source side:
        #   path[0] -> path[1] -> ... -> middle
        #
        # Destination side:
        #   path[-1] -> path[-2] -> ... -> middle
        # ------------------------------------------------------------
        preparation_links = []

        # Source -> middle
        for i in range(0, middle_index):
            preparation_links.append(
                (path[i], path[i + 1])
            )

        # Destination -> middle
        for i in range(len(path) - 1, middle_index, -1):
            preparation_links.append(
                (path[i], path[i - 1])
            )

        self.twh_total_links = len(preparation_links)

        # Store total on every app
        for node_name in path:
            node = self.node.timeline.get_entity_by_name(node_name)
            node.teleport_app.twh_total_links = self.twh_total_links

        # ------------------------------------------------------------
        # START ALL PREPARATION LINKS
        # ------------------------------------------------------------
        for current_node, next_node in preparation_links:

            current_app = self.node.timeline.get_entity_by_name(
                current_node
            ).teleport_app

            current_app._start_twh_preparation(
                responder=next_node,
                start_t=start_t,
                end_t=end_t,
                memory_size=memory_size,
                fidelity=fidelity,
                data_memory_index=data_memory_index
            )

    def _start_twh_preparation(
        self,
        responder,
        start_t,
        end_t,
        memory_size,
        fidelity,
        data_memory_index
    ):
        """
        Start one EPR preparation link for TWH.
        No data teleportation happens here.
        """

        super().start(
            responder=responder,
            start_t=start_t,
            end_t=end_t,
            memo_size=memory_size,
            fidelity=fidelity
        )

        teleport_protocol = TeleportProtocol(
            self.node,
            alice=True,
            data_memory_index=data_memory_index,
            remote_node_name=responder
        )

        teleport_protocol.twh_preparation = True
        teleport_protocol.twh_prepared = False
        teleport_protocol.twh_reservation = None

        self.teleport_protocols.append(
            teleport_protocol
        )

        self.twh_preparation_protocols.append(
            teleport_protocol
        )

        root = self.twh_root_app

        if root is not None:
            root.twh_preparation_map[
                (self.node.name, responder)
            ] = {
                "alice_protocol": teleport_protocol,
                "bob_protocol": None,
                "alice_ready": False,
                "bob_ready": False,
                "counted": False
            }

    def _twh_link_ready(self, key):
        root = self.twh_root_app

        if root is None:
            root = self

        entry = root.twh_preparation_map.get(key)

        if entry is None:
            return

        if entry["counted"]:
            return

        if not entry["alice_ready"]:
            return

        if not entry["bob_ready"]:
            return

        entry["counted"] = True

        root.twh_prepared_count += 1

        if root.twh_prepared_count == root.twh_total_links:

            root.twh_preparation = False
            root.twh_prepared = True

            root._start_twh_data_phase(
                start_t=root.node.timeline.now()
                + 100_000_000,
                end_t=root.node.timeline.now()
                + 100_000_000_000,
                memory_size=1,
                fidelity=0.9,
                data_memory_index=0
            )
    def _start_twh_data_phase(
        self,
        start_t,
        end_t,
        memory_size,
        fidelity,
        data_memory_index
    ):
        path = self.twh_path
        middle_index = len(path) // 2

        self.twh_data_protocols = {}

        for i in range(len(path) - 1):

            current_node = path[i]
            next_node = path[i + 1]

            current_app = self.node.timeline.get_entity_by_name(
                current_node
            ).teleport_app

            next_app = self.node.timeline.get_entity_by_name(
                next_node
            ).teleport_app

            # ========================================================
            # LEFT SIDE
            # Preparation was current -> next
            # ========================================================
            if i < middle_index:

                key = (current_node, next_node)
                entry = self.twh_preparation_map[key]

                prep_protocol = entry["alice_protocol"]

                reservation = prep_protocol.twh_reservation

                # -----------------------------
                # Alice = current node
                # -----------------------------
                alice_protocol = TeleportProtocol(
                    current_app.node,
                    alice=True,
                    data_memory_index=data_memory_index,
                    remote_node_name=next_node
                )

                alice_protocol.twh_data = True
                alice_protocol.twh_edge = (
                    current_node,
                    next_node
                )
                alice_protocol.twh_reservation = reservation

                alice_protocol.set_alice_comm_memory(
                    prep_protocol.alice_comm_memory
                )

                alice_protocol.set_alice_comm_memory_name(
                    prep_protocol.alice_comm_memory.name
                )

                alice_protocol.set_bob_comm_memory_name(
                    prep_protocol.bob_comm_memory_name
                )

                current_app.teleport_protocols.append(
                    alice_protocol
                )

                # -----------------------------
                # Bob = next node
                # -----------------------------
                bob_protocol = TeleportProtocol(
                    next_app.node,
                    alice=False,
                    remote_node_name=current_node
                )

                bob_protocol.twh_data = True
                bob_protocol.twh_edge = (
                    current_node,
                    next_node
                )
                bob_protocol.twh_reservation = reservation

                bob_protocol.set_bob_comm_memory_name(
                    prep_protocol.bob_comm_memory_name
                )

                # Find Bob's actual memory from preparation
                prep_entry = entry["bob_protocol"]

                if prep_entry is not None:
                    bob_protocol.set_bob_comm_memory(
                        prep_entry.bob_comm_memory
                    )
                    bob_protocol.set_alice_comm_memory_name(
                        prep_entry.alice_comm_memory_name
                    )

                next_app.teleport_protocols.append(
                    bob_protocol
                )

                self.twh_data_protocols[
                    (current_node, next_node)
                ] = alice_protocol

            # ========================================================
            # RIGHT SIDE
            # Preparation was next -> current
            # ========================================================
            else:

                key = (next_node, current_node)
                entry = self.twh_preparation_map[key]

                prep_alice = entry["alice_protocol"]
                prep_bob = entry["bob_protocol"]

                reservation = prep_bob.twh_reservation

                # -----------------------------
                # Alice = current node
                # Uses its Bob half from preparation
                # -----------------------------
                alice_protocol = TeleportProtocol(
                    current_app.node,
                    alice=True,
                    data_memory_index=data_memory_index,
                    remote_node_name=next_node
                )

                alice_protocol.twh_data = True
                alice_protocol.twh_edge = (
                    current_node,
                    next_node
                )
                alice_protocol.twh_reservation = reservation

                alice_protocol.set_alice_comm_memory(
                    prep_bob.bob_comm_memory
                )

                alice_protocol.set_alice_comm_memory_name(
                    prep_bob.bob_comm_memory.name
                )

                alice_protocol.set_bob_comm_memory_name(
                    prep_alice.alice_comm_memory.name
                )

                current_app.teleport_protocols.append(
                    alice_protocol
                )

                # -----------------------------
                # Bob = next node
                # Uses Alice half from preparation
                # -----------------------------
                bob_protocol = TeleportProtocol(
                    next_app.node,
                    alice=False,
                    remote_node_name=current_node
                )

                bob_protocol.twh_data = True
                bob_protocol.twh_edge = (
                    current_node,
                    next_node
                )
                bob_protocol.twh_reservation = reservation

                bob_protocol.set_bob_comm_memory(
                    prep_alice.alice_comm_memory
                )

                bob_protocol.set_bob_comm_memory_name(
                    prep_alice.alice_comm_memory.name
                )

                bob_protocol.set_alice_comm_memory_name(
                    prep_bob.bob_comm_memory.name
                )

                next_app.teleport_protocols.append(
                    bob_protocol
                )

                self.twh_data_protocols[
                    (current_node, next_node)
                ] = alice_protocol

        # ============================================================
        # Start ONLY first DATA hop
        # ============================================================
        first_protocol = self.twh_data_protocols[
            (path[0], path[1])
        ]

        process = Process(
            first_protocol,
            "alice_bell_measurement",
            [first_protocol.twh_reservation]
        )

        event = Event(
            self.node.timeline.now(),
            process
        )

        self.node.timeline.schedule(event)
    def _start_next_hop(
        self,
        start_t,
        end_t,
        memory_size,
        fidelity,
        data_memory_index,
        source_comm_memory=None
    ):
        if self.hh_index >= len(self.hh_path) - 1:
            return

        current_node = self.hh_path[self.hh_index]
        next_node = self.hh_path[self.hh_index + 1]

        # This app must belong to current node
        if self.node.name != current_node:
            return

        super().start(
                    next_node,
                    start_t,
                    end_t,
                    memory_size,
                    fidelity
                )

        teleport_protocol = TeleportProtocol(
            self.node,
            alice=True,
            data_memory_index=data_memory_index,
            remote_node_name=next_node
        )

        teleport_protocol.source_comm_memory = source_comm_memory

        # Store hop information
        teleport_protocol.hh_path = self.hh_path
        teleport_protocol.hh_index = self.hh_index

        self.teleport_protocols.append(teleport_protocol)
    def _start_twh_direction(
        self,
        path,
        start_t,
        end_t,
        memory_size,
        fidelity,
        data_memory_index,
        source_comm_memory=None
    ):
        if self.twh_index >= len(path) - 1:
            return

        current_node = path[self.twh_index]
        next_node = path[self.twh_index + 1]

        if self.node.name != current_node:
            return

        super().start(
            responder=next_node,
            start_t=start_t,
            end_t=end_t,
            memory_size=memory_size,
            fidelity=fidelity
        )

        teleport_protocol = TeleportProtocol(
            self.node,
            alice=True,
            data_memory_index=data_memory_index,
            remote_node_name=next_node
        )

        teleport_protocol.source_comm_memory = source_comm_memory

        self.teleport_protocols.append(teleport_protocol)
    def get_reservation_result(self, reservation, result: bool):
        """Handle the reservation result from the network manager.

        Args:
            reservation (Reservation): The reservation object.
            result (bool): True if the reservation was successful, False otherwise.
        """
        super().get_reservation_result(reservation, result)
        log.logger.debug(f"{self.name}: reservation_result -> {result}")

    def get_memory(self, info: MemoryInfo):
        """Handle memory state changes.

        Args:
            info (MemoryInfo): Information about the memory state change.
        """

        print(info)
        log.logger.debug(
            f"{self.name}: get_memory, "
            f"name={info.memory.name}, state={info.state}"
        )

        if info.index not in self.memo_to_reservation:
            return

        if info.state != "ENTANGLED":
            return

        print(
            ">>> ENTANGLED ENTERED:",
            self.node.name,
            info.memory.name
        )

        reservation = self.memo_to_reservation[info.index]

        this_node = info.memory.owner.name
        remote_node = info.remote_node

        # ============================================================
        # 1. CHECK EXISTING ALICE PROTOCOL
        # ============================================================

        for teleport_protocol in self.teleport_protocols:

            if (
                teleport_protocol.alice
                and teleport_protocol.owner.name == this_node
                and teleport_protocol.remote_node_name == remote_node
            ):

                print(">>> ALICE PROTOCOL MATCHED")

                teleport_protocol.set_alice_comm_memory_name(
                    info.memory.name
                )

                teleport_protocol.set_alice_comm_memory(
                    info.memory
                )

                teleport_protocol.set_bob_comm_memory_name(
                    info.remote_memo
                )

                # ====================================================
                # TWH PREPARATION
                # ====================================================

                if getattr(
                    teleport_protocol,
                    "twh_preparation",
                    False
                ):

                    teleport_protocol.twh_reservation = reservation
                    teleport_protocol.twh_prepared = True

                    root = self.twh_root_app

                    if root is None:
                        root = self

                    key = (
                        reservation.initiator,
                        reservation.responder
                    )

                    entry = root.twh_preparation_map.get(key)

                    if entry is not None:

                        entry["alice_ready"] = True

                        if entry["bob_ready"]:
                            root._twh_link_ready(key)

                    break

                # ====================================================
                # NORMAL HH / NORMAL TELEPORT
                # ====================================================

                process = Process(
                    teleport_protocol,
                    "alice_bell_measurement",
                    [reservation]
                )

                event = Event(
                    self.node.timeline.now(),
                    process,
                    self.node.timeline.schedule_counter
                )

                self.node.timeline.schedule(event)

                break

        else:

            # ========================================================
            # 2. NO ALICE PROTOCOL FOUND
            #    → THIS IS BOB SIDE
            # ========================================================

            if self.node.name != reservation.responder:
                print(">>> NOT BOB - SKIPPING BOB PROTOCOL")
                return

            print(">>> BOB SIDE: CREATING TELEPORT PROTOCOL")

            teleport_protocol = TeleportProtocol(
                self.node,
                alice=False,
                remote_node_name=reservation.initiator
            )

            teleport_protocol.set_bob_comm_memory_name(
                info.memory.name
            )

            teleport_protocol.set_bob_comm_memory(
                info.memory
            )

            teleport_protocol.set_alice_comm_memory_name(
                info.remote_memo
            )

            # ========================================================
            # TWH PREPARATION
            # ========================================================

            # Only mark this as TWH preparation if the root has
            # a preparation entry for this reservation.
            root = self.twh_root_app

            if (
                root is not None
                and hasattr(root, "twh_preparation_map")
            ):

                key = (
                    reservation.initiator,
                    reservation.responder
                )

                if key in root.twh_preparation_map:

                    teleport_protocol.twh_preparation = True
                    teleport_protocol.twh_prepared = True
                    teleport_protocol.twh_reservation = reservation

                    self.teleport_protocols.append(
                        teleport_protocol
                    )

                    root.twh_preparation_map[key][
                        "bob_protocol"
                    ] = teleport_protocol

                    root.twh_preparation_map[key][
                        "bob_ready"
                    ] = True

                    root._twh_link_ready(key)

                    return

            # ========================================================
            # NORMAL HH / NORMAL TELEPORT BOB
            # ========================================================

            teleport_protocol.twh_preparation = False

            self.teleport_protocols.append(
                teleport_protocol
            )
    def received_message(self, src: str, msg: TeleportMessage):
        """Handle incoming teleport messages.

        Args:
            src (str): Source node name.
            msg (TeleportMessage): The teleport message received.
        """
        log.logger.debug(f"{self.name} received_message from {src}: {msg}")
        if msg.msg_type is TeleportMsgType.MEASUREMENT_RESULT:

        # TWH DATA protocol must be matched first
            for teleport_protocol in reversed(self.teleport_protocols):

                if (
                    not teleport_protocol.alice
                    and getattr(teleport_protocol, "twh_data", False)
                    and teleport_protocol.twh_reservation == msg.reservation
                ):
                    teleport_protocol.received_message(src, msg)

                    self.node.resource_manager.expire_rules_by_reservation(
                        msg.reservation
                    )

                    teleport_protocol.bob_acknowledge_complete(
                        msg.reservation
                    )

                    self.teleport_protocols.remove(
                        teleport_protocol
                    )

                    break

            else:

                # Normal HH / normal teleport
                for teleport_protocol in self.teleport_protocols:

                    if not teleport_protocol.alice:
                        teleport_protocol.received_message(src, msg)

                        self.node.resource_manager.expire_rules_by_reservation(
                            msg.reservation
                        )

                        teleport_protocol.bob_acknowledge_complete(
                            msg.reservation
                        )

                        self.teleport_protocols.remove(
                            teleport_protocol
                        )

                        break

                else:
                    log.logger.warning(
                        f"{self.name}: received_message: no matching Bob teleport protocol "
                        f"for msg={msg} from {src}"
                    )
        elif msg.msg_type is TeleportMsgType.ACK:              # Alice receives acknowledgment from Bob
            for teleport_protocol in self.teleport_protocols:  # find the correct teleport protocol on Alice's side
                if msg.bob_comm_memory_name == teleport_protocol.bob_comm_memory_name:
                    self.node.resource_manager.expire_rules_by_reservation(msg.reservation)                      # expire the rules
                    self.node.resource_manager.update(None, teleport_protocol.alice_comm_memory, MemoryInfo.RAW) # release the alice comm memory
                    self.teleport_protocols.remove(teleport_protocol)  # remove the protocol instance, it's lifecycle is complete
                    break
            else:
                log.logger.warning(f"{self.name}: received_message: no matching teleport protocol for msg={msg} from {src}")
    def teleport_complete(self, comm_key: int, received_memory=None):
        my_qubit = self.node.timeline.quantum_manager.get(comm_key)
        psi = my_qubit.state

        log.logger.info(f"{self.name}: teleport done, state={psi}")
        self.results.append((self.node.timeline.now(), psi))

        # ============================================================
        # HH: start next hop using the teleported qubit
        # ============================================================
        if self.hh_active and self.hh_path is not None:
            print("HH NEXT HOP TRIGGERED:", self.node.name, self.hh_index)

            current_index = self.hh_index

            if current_index < len(self.hh_path) - 1:
                self.hh_index = current_index

                self._start_next_hop(
                    start_t=self.node.timeline.now() + 100_000_000,
                    end_t=self.node.timeline.now() + 100_000_000_000,
                    memory_size=1,
                    fidelity=0.9,
                    data_memory_index=0,
                    source_comm_memory=received_memory
                )

                # ============================================================
        # TWH DATA: continue using pre-prepared EPR
        # ============================================================
        root = self.twh_root_app
        if (
            self.twh_active
            and self.twh_path is not None
            and root is not None
            and hasattr(self, "twh_data_protocols")
        ):

            current_index = self.twh_index

            if current_index < len(self.twh_path) - 1:

                current_node = self.twh_path[current_index]
                next_node = self.twh_path[current_index + 1]

                protocol = root.twh_data_protocols.get(
                    (current_node, next_node)
                )

                if protocol is not None:

                    # The qubit received from the previous hop
                    # becomes the data qubit for this hop.
                    protocol.source_comm_memory = received_memory

                    process = Process(
                        protocol,
                        "alice_bell_measurement",
                        [protocol.twh_reservation]
                    )

                    event = Event(
                        self.node.timeline.now()
                        + 100_000_000,
                        process
                    )

                    self.node.timeline.schedule(event)