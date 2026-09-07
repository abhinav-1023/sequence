from typing import TYPE_CHECKING, Any

from .generation_message import EntanglementGenerationMessage, GenerationMsgType, valid_trigger_time

if TYPE_CHECKING:
    from ...components.memory import Memory
    from ...topology.node import Node, BSMNode
    from ...components.bsm import SingleAtomBSM

from ...resource_management.memory_manager import MemoryInfo
from ...constants import BARRET_KOK
from .generation_base import EntanglementGenerationA, EntanglementGenerationB, QuantumCircuitMixin

from ...kernel.event import Event
from ...kernel.process import Process
from ...utils import log, metrics
from ...utils.metrics.event_types import EventTypes


@EntanglementGenerationA.register(BARRET_KOK)
class BarretKokA(EntanglementGenerationA, QuantumCircuitMixin):
    """Entanglement generation protocol for quantum router.

    The EntanglementGenerationA protocol should be instantiated on a quantum router node.
    Instances will communicate with each other (and with the B instance on a BSM node) to generate entanglement.

    Attributes:
        owner (QuantumRouter): node that protocol instance is attached to.
        name (str): label for protocol instance.
        middle (str): name of BSM measurement node where emitted photons should be directed.
        remote_node_name (str): name of distant QuantumRouter node, containing a memory to be entangled with local memory.
        memory (Memory): quantum memory object to attempt entanglement for.
    """

    def __init__(self, owner: "Node", name: str, middle: str, other: str, memory: "Memory", **kwargs: Any):
        """Constructor for entanglement generation A class.

        Args:
            owner (Node): node to attach protocol to.
            name (str): name of protocol instance.
            middle (str): name of middle measurement node.
            other (str): name of other node.
            memory (Memory): memory to entangle.
        """

        # raise error if passed kwargs
        if kwargs:
            raise ValueError(f"Unexpected keyword arguments: {kwargs}")

        super().__init__(owner, name, middle, other, memory)
        self.protocol_type = BARRET_KOK
        self.bsm_res = [-1, -1]
        self.fidelity: float = memory.raw_fidelity

    def update_memory(self) -> bool | None:
        """Method to handle necessary memory operations.

        Called on both nodes.
        Will check the state of the memory and protocol.

        Returns:
            bool: if current round was successful.

        Side Effects:
            May change state of attached memory.
            May update memory state in the attached node's resource manager.
        """

        # to avoid start after protocol removed

        if self not in self.owner.protocols:
            return

        self.ent_round += 1

        if self.ent_round == 1:
            return True

        elif self.ent_round == 2 and self.bsm_res[0] != -1:
            self.owner.timeline.quantum_manager.run_circuit(self._flip_circuit, [self._qstate_key])
            return True

        elif self.ent_round == 3 and self.bsm_res[1] != -1:
            print("\n===== BK SUCCESS CHECK =====")
            print("Node        :", self.owner.name)
            print("Protocol    :", self.name)
            print("Memory      :", self.memory.name)
            print("Primary     :", self.primary)
            print("BSM RES     :", self.bsm_res)
            print("Remote      :", self.remote_node_name)
            print("============================")
            # entanglement succeeded, correction
            if self.primary:
                self.owner.timeline.quantum_manager.run_circuit(self._flip_circuit, [self._qstate_key])
            elif self.bsm_res[0] != self.bsm_res[1]:
                self.owner.timeline.quantum_manager.run_circuit(self._z_circuit, [self._qstate_key])
            self._entanglement_succeed()
            return True

        else:
            # entanglement failed
            print("\n===== BK FAILED =====")
            print("Node     :", self.owner.name)
            print("Protocol :", self.name)
            print("Round    :", self.ent_round)
            print("BSM RES  :", self.bsm_res)
            print("====================")
            self._entanglement_fail()
            return False

    def emit_event(self) -> None:
        print("\n===== BARRETT-KOK EMIT =====")
        print("Node       :", self.owner.name)
        print("Protocol   :", self.name)
        print("Memory     :", self.memory.name)
        print("Middle BSM :", self.middle)
        print("Ent round  :", self.ent_round)
        print("Ready?     :", self.is_ready())

        log.logger.debug(
            f"{self.owner.name}: BK emit_event "
            f"protocol={self.name}, memory={self.memory.name}, "
            f"middle={self.middle}, round={self.ent_round}"
        )

        if not self.is_ready():
            print("!!! EMIT FAILED: protocol not ready !!!")
            log.logger.info(f'{self} is not valid, emit_event() failed.')
            return

        if self.ent_round == 1:
            print("Setting memory to |+> state")
            self.memory.update_state(self._plus_state)

        print("Calling memory.excite()")

        self.memory.excite(self.middle)

        print("===== EMIT DONE =====\n")

    def received_message(self, src: str, msg: EntanglementGenerationMessage) -> None:
        """Method to receive messages.

        This method receives messages from other entanglement generation protocols.
        Depending on the message, different actions may be taken by the protocol.

        Args:
            src (str): name of the source node sending the message.
            msg (EntanglementGenerationMessage): message received.

        Side Effects:
            May schedule various internal and hardware events.
        """
        print(
        f"[BK RECEIVED] node={self.owner.name}, "
        f"memory={self.memory.name}, "
        f"ent_round={self.ent_round}, "
        f"remote={self.remote_node_name}, "
        f"middle={self.middle}, "
        f"msg={msg.msg_type}"
    )
        print("\n========== BK RECEIVED MESSAGE ==========")
        print("Node     :", self.owner.name)
        print("Protocol :", self.name)
        print("Source   :", src)
        print("Msg type :", msg.msg_type)
        print("Round    :", self.ent_round)
        print("========================================")

        if src not in [self.middle, self.remote_node_name]:
            return

        msg_type = msg.msg_type

        log.logger.debug("{} {} received message from node {} of type {}, round={}".format(
            self.owner.name, self.name, src, msg.msg_type, self.ent_round))

        if msg_type is GenerationMsgType.NEGOTIATE:  # primary -> non-primary
            # configure params
            other_qc_delay = msg.qc_delay
            self.qc_delay = self.owner.qchannels[self.middle].delay
            cc_delay = int(self.owner.cchannels[src].delay)

            # get time for first excite event
            memory_excite_time = self.memory.next_excite_time
            min_time = max(self.owner.timeline.now(),
                           memory_excite_time) + other_qc_delay - self.qc_delay + cc_delay  # cc_delay time for NEGOTIATE_ACK
            emit_time = self.owner.schedule_qubit(self.middle, min_time)  # used to send memory
            print("\n===== BK NEGOTIATE SCHEDULE =====")
            print("Node          :", self.owner.name)
            print("ent_round     :", self.ent_round)
            print("now           :", self.owner.timeline.now())
            print("memory_excite :", memory_excite_time)
            print("min_time      :", min_time)
            print("emit_time     :", emit_time)
            print("qc_delay      :", self.qc_delay)
            print("=================================")
            self.expected_time = emit_time + self.qc_delay  # expected time for middle BSM node to receive the photon

            # schedule emit
            process = Process(self, "emit_event", [])
            event = Event(emit_time, process)
            self.owner.timeline.schedule(event)
            self.scheduled_events.append(event)

            # send negotiate_ack
            other_emit_time = emit_time + self.qc_delay - other_qc_delay
            message = EntanglementGenerationMessage(GenerationMsgType.NEGOTIATE_ACK,
                                                    self.remote_protocol_name,
                                                    protocol_type=self.protocol_type,
                                                    emit_time=other_emit_time)
            self.owner.send_message(src, message)

            # schedule start if necessary (current is first round, need second round),
            # else schedule update_memory (currently second round)
            # TODO: base future start time on resolution
            future_start_time = self.expected_time + self.owner.cchannels[
                self.middle].delay + 10  # delay is for sending the BSM_RES to end nodes, 10 is a small gap
            print("\n===== BK FUTURE EVENT =====")
            print("Node              :", self.owner.name)
            print("ent_round         :", self.ent_round)
            print("expected_time     :", self.expected_time)
            print("future_start_time :", future_start_time)
            print("timeline now      :", self.owner.timeline.now())
            print("================================")
            if self.ent_round == 1:
                process = Process(self, "start", [])  # for the second round
            else:
                process = Process(self, "update_memory", [])
            priority = self.owner.timeline.schedule_counter
            event = Event(future_start_time, process, priority)
            self.owner.timeline.schedule(event)
            self.scheduled_events.append(event)
            print(">>> EVENT SCHEDULED")
            print("Node :", self.owner.name)
            print("Event time :", event.time)
            print("Process :", event.process.activation)
            print("==========================")

        elif msg_type is GenerationMsgType.NEGOTIATE_ACK:  # non-primary --> primary
            # configure params
            self.expected_time = msg.emit_time + self.qc_delay  # expected time for middle BSM node to receive the photon

            if msg.emit_time < self.owner.timeline.now():  # emit time calculated by the non-primary node
                msg.emit_time = self.owner.timeline.now()

            # schedule emit
            emit_time = self.owner.schedule_qubit(self.middle, msg.emit_time)
            print("\n===== BK NEGOTIATE_ACK SCHEDULE =====")
            print("Node          :", self.owner.name)
            print("ent_round     :", self.ent_round)
            print("now           :", self.owner.timeline.now())
            print("msg.emit_time :", msg.emit_time)
            print("emit_time     :", emit_time)
            print("expected_time :", self.expected_time)
            print("=====================================")
            assert emit_time == msg.emit_time, f"Invalid eg emit times {emit_time} {msg.emit_time} {self.owner.timeline.now()}"

            process = Process(self, "emit_event", [])
            event = Event(msg.emit_time, process)
            self.owner.timeline.schedule(event)
            self.scheduled_events.append(event)

            # schedule start if necessary (current is first round, need second round),
            # else schedule update_memory (currently second round)
            # TODO: base future start time on resolution
            future_start_time = self.expected_time + self.owner.cchannels[self.middle].delay + 10
            print(">>> NEGOTIATE_ACK FUTURE EVENT")
            print("Node :", self.owner.name)
            print("future_start_time :", future_start_time)
            print("process :", process.activation)
            if self.ent_round == 1:
                process = Process(self, "start", [])  # for the second round
            else:
                process = Process(self, "update_memory", [])
            priority = self.owner.timeline.schedule_counter
            event = Event(future_start_time, process, priority)
            self.owner.timeline.schedule(event)
            self.scheduled_events.append(event)

        elif msg_type is GenerationMsgType.MEAS_RES:  # from middle BSM to both non-primary and primary
            detector = msg.detector
            time = msg.time
            resolution = msg.resolution

            log.logger.debug("{} received MEAS_RES={} at time={:,}, expected={:,}, resolution={}, round={}".format(
                self.owner.name, detector, time, self.expected_time, resolution, self.ent_round))

            if valid_trigger_time(time, self.expected_time, resolution):
                # record result if we don't already have one
                i = self.ent_round - 1
                if self.bsm_res[i] == -1:
                    self.bsm_res[i] = detector  # save the measurement results (detector number)
                else:
                    self.bsm_res[i] = -1  # BSM measured 1, 1 (both photons kept)
            else:
                log.logger.debug(f'{self.owner.name} BSM trigger time not valid')

        else:
            raise Exception(f"Invalid message {msg_type} received by EG on node {self.owner.name}")

    def _entanglement_succeed(self):
        self.memory.entangled_memory['node_id'] = self.remote_node_name
        self.memory.entangled_memory['memo_id'] = self.remote_memo_id
        self.memory.fidelity = self.memory.raw_fidelity

        print("\n===== ENTANGLEMENT SUCCESS =====")
        print("Node        :", self.owner.name)
        print("Remote Node :", self.remote_node_name)
        print("Memory      :", self.memory.name)
        print("Fidelity    :", self.memory.fidelity)
        print("===============================\n")
        metrics.record(
            EventTypes.EG_SUCCESS,
            self.owner.name,
            remote_node=self.remote_node_name,
            fidelity=self.fidelity,
        )
        self.update_resource_manager(self.memory, MemoryInfo.ENTANGLED)


@EntanglementGenerationB.register(BARRET_KOK)
class BarretKokB(EntanglementGenerationB):
    """Entanglement generation protocol for BSM node.

    The EntanglementGenerationB protocol should be instantiated on a BSM node.
    Instances will communicate with the A instance on neighboring quantum router nodes to generate entanglement.

    Attributes:
        owner (BSMNode): node that protocol instance is attached to.
        name (str): label for protocol instance.
        others (list[str]): list of neighboring quantum router nodes
    """

    def __init__(self, owner: "BSMNode", name: str, others: list[str]):
        """Constructor for entanglement generation B protocol.

        Args:
            owner (Node): attached node.
            name (str): name of protocol instance.
            others (list[str]): name of protocol instance on end nodes.
        """
        super().__init__(owner, name, others)
        self.protocol_type = BARRET_KOK

    def bsm_update(self, bsm: "SingleAtomBSM", info: dict[str, Any]):
        print(f"[BKB UPDATE] {self.owner.name} received BSM result: {info}")
        assert info['info_type'] == "BSM_res"

        res = info["res"]
        time = info["time"]
        resolution = bsm.resolution

        for node in self.others:
            print(f"[BKB SEND] {self.owner.name} -> {node}, detector={res}")
            message = EntanglementGenerationMessage(GenerationMsgType.MEAS_RES,
                                                    receiver=None,  # receiver is None (not paired)
                                                    protocol_type=self.protocol_type,
                                                    detector=res,
                                                    time=time,
                                                    resolution=resolution)
            self.owner.send_message(node, message)
