from __future__ import annotations

from dataclasses import dataclass, field
import os
from typing import Any, Dict, List, Optional, Protocol, Sequence
from uuid import uuid4

import grpc

from .openshell_grpc.gen import openshell_draft_pb2, openshell_draft_pb2_grpc, sandbox_pb2


@dataclass(frozen=True)
class DraftPolicyChunk:
    id: str
    status: str  # "pending" | "approved" | "rejected"
    rule_name: str
    proposed_rule: Dict[str, Any]
    rationale: str = ""
    security_notes: str = ""
    confidence: float = 0.0
    denial_summary_ids: Sequence[str] = ()


@dataclass(frozen=True)
class DraftPolicy:
    sandbox_name: str
    draft_version: int
    chunks: Sequence[DraftPolicyChunk] = ()
    rolling_summary: str = ""


class OpenShellClient(Protocol):
    """
    Minimal interface for Phase 1A (draft policy governance).

    A real implementation can be backed by OpenShell gRPC:
      - GetDraftPolicy
      - ApproveDraftChunk / RejectDraftChunk / EditDraftChunk
      - ApproveAllDraftChunks / ClearDraftChunks
      - GetDraftHistory (optional)
    """

    def get_draft_policy(
        self, *, sandbox_name: str, status_filter: str = ""
    ) -> DraftPolicy: ...

    def approve_draft_chunk(self, *, sandbox_name: str, chunk_id: str) -> Dict[str, Any]: ...

    def reject_draft_chunk(
        self, *, sandbox_name: str, chunk_id: str, reason: str = ""
    ) -> Dict[str, Any]: ...

    def edit_draft_chunk(
        self, *, sandbox_name: str, chunk_id: str, proposed_rule: Dict[str, Any]
    ) -> Dict[str, Any]: ...

    def approve_all_draft_chunks(
        self, *, sandbox_name: str, include_security_flagged: bool = False
    ) -> Dict[str, Any]: ...

    def clear_draft_chunks(self, *, sandbox_name: str) -> Dict[str, Any]: ...


@dataclass
class GrpcOpenShellClient:
    endpoint: str
    timeout_seconds: float = 15.0
    tls_ca_path: Optional[str] = None
    tls_cert_path: Optional[str] = None
    tls_key_path: Optional[str] = None
    tls_target_name: Optional[str] = None

    def __post_init__(self) -> None:
        if self.tls_ca_path and self.tls_cert_path and self.tls_key_path:
            with open(self.tls_ca_path, "rb") as f:
                ca = f.read()
            with open(self.tls_cert_path, "rb") as f:
                cert = f.read()
            with open(self.tls_key_path, "rb") as f:
                key = f.read()
            creds = grpc.ssl_channel_credentials(root_certificates=ca, private_key=key, certificate_chain=cert)
            options = []
            if self.tls_target_name:
                options.append(("grpc.ssl_target_name_override", self.tls_target_name))
                # Ensure :authority matches the override for hostname verification.
                options.append(("grpc.default_authority", self.tls_target_name))
            self._channel = grpc.secure_channel(self.endpoint, creds, options=options)
        else:
            self._channel = grpc.insecure_channel(self.endpoint)
        self._stub = openshell_draft_pb2_grpc.OpenShellStub(self._channel)

    def close(self) -> None:
        self._channel.close()

    def get_draft_policy(self, *, sandbox_name: str, status_filter: str = "") -> DraftPolicy:
        resp = self._stub.GetDraftPolicy(
            openshell_draft_pb2.GetDraftPolicyRequest(name=sandbox_name, status_filter=status_filter),
            timeout=self.timeout_seconds,
        )
        chunks = [
            DraftPolicyChunk(
                id=c.id,
                status=c.status,
                rule_name=c.rule_name,
                proposed_rule=_network_rule_to_dict(c.proposed_rule),
                rationale=c.rationale,
                security_notes=c.security_notes,
                confidence=float(c.confidence),
                denial_summary_ids=tuple(c.denial_summary_ids),
            )
            for c in resp.chunks
        ]
        return DraftPolicy(
            sandbox_name=sandbox_name,
            draft_version=int(resp.draft_version),
            chunks=chunks,
            rolling_summary=resp.rolling_summary,
        )

    def approve_draft_chunk(self, *, sandbox_name: str, chunk_id: str) -> Dict[str, Any]:
        resp = self._stub.ApproveDraftChunk(
            openshell_draft_pb2.ApproveDraftChunkRequest(name=sandbox_name, chunk_id=chunk_id),
            timeout=self.timeout_seconds,
        )
        return {"ok": True, "policy_version": int(resp.policy_version), "policy_hash": resp.policy_hash}

    def reject_draft_chunk(self, *, sandbox_name: str, chunk_id: str, reason: str = "") -> Dict[str, Any]:
        self._stub.RejectDraftChunk(
            openshell_draft_pb2.RejectDraftChunkRequest(name=sandbox_name, chunk_id=chunk_id, reason=reason),
            timeout=self.timeout_seconds,
        )
        return {"ok": True}

    def edit_draft_chunk(
        self, *, sandbox_name: str, chunk_id: str, proposed_rule: Dict[str, Any]
    ) -> Dict[str, Any]:
        rule_msg = _dict_to_network_rule(proposed_rule)
        self._stub.EditDraftChunk(
            openshell_draft_pb2.EditDraftChunkRequest(name=sandbox_name, chunk_id=chunk_id, proposed_rule=rule_msg),
            timeout=self.timeout_seconds,
        )
        return {"ok": True}

    def approve_all_draft_chunks(
        self, *, sandbox_name: str, include_security_flagged: bool = False
    ) -> Dict[str, Any]:
        resp = self._stub.ApproveAllDraftChunks(
            openshell_draft_pb2.ApproveAllDraftChunksRequest(
                name=sandbox_name, include_security_flagged=include_security_flagged
            ),
            timeout=self.timeout_seconds,
        )
        return {
            "ok": True,
            "policy_version": int(resp.policy_version),
            "policy_hash": resp.policy_hash,
            "chunks_approved": int(resp.chunks_approved),
            "chunks_skipped": int(resp.chunks_skipped),
        }

    def clear_draft_chunks(self, *, sandbox_name: str) -> Dict[str, Any]:
        resp = self._stub.ClearDraftChunks(
            openshell_draft_pb2.ClearDraftChunksRequest(name=sandbox_name),
            timeout=self.timeout_seconds,
        )
        return {"ok": True, "chunks_cleared": int(resp.chunks_cleared)}


def _network_rule_to_dict(rule: sandbox_pb2.NetworkPolicyRule) -> Dict[str, Any]:
    return {
        "name": rule.name,
        "endpoints": [
            {
                "host": e.host,
                "port": int(e.port),
                "ports": [int(p) for p in e.ports],
                "protocol": e.protocol,
                "tls": e.tls,
                "enforcement": e.enforcement,
                "access": e.access,
                "allowed_ips": list(e.allowed_ips),
            }
            for e in rule.endpoints
        ],
        "binaries": [{"path": b.path} for b in rule.binaries],
    }


def _dict_to_network_rule(data: Dict[str, Any]) -> sandbox_pb2.NetworkPolicyRule:
    rule = sandbox_pb2.NetworkPolicyRule()
    rule.name = str(data.get("name", ""))
    for e in data.get("endpoints", []) or []:
        ep = rule.endpoints.add()
        ep.host = str(e.get("host", ""))
        if "ports" in e and isinstance(e["ports"], list):
            ep.ports.extend([int(p) for p in e["ports"]])
        elif "port" in e:
            ep.port = int(e["port"])
        if "protocol" in e:
            ep.protocol = str(e.get("protocol") or "")
        if "tls" in e:
            ep.tls = str(e.get("tls") or "")
        if "enforcement" in e:
            ep.enforcement = str(e.get("enforcement") or "")
        if "access" in e:
            ep.access = str(e.get("access") or "")
        if "allowed_ips" in e and isinstance(e["allowed_ips"], list):
            ep.allowed_ips.extend([str(x) for x in e["allowed_ips"]])
    for b in data.get("binaries", []) or []:
        bi = rule.binaries.add()
        bi.path = str(b.get("path", ""))
    return rule


def create_openshell_client() -> OpenShellClient:
    endpoint = os.environ.get("STEWARD_OPENSHELL_GRPC_ENDPOINT", "").strip()
    if endpoint:
        ca = os.environ.get("STEWARD_OPENSHELL_TLS_CA_PATH")
        cert = os.environ.get("STEWARD_OPENSHELL_TLS_CERT_PATH")
        key = os.environ.get("STEWARD_OPENSHELL_TLS_KEY_PATH")
        target = os.environ.get("STEWARD_OPENSHELL_TLS_TARGET_NAME")
        return GrpcOpenShellClient(
            endpoint=endpoint,
            tls_ca_path=ca,
            tls_cert_path=cert,
            tls_key_path=key,
            tls_target_name=target,
        )
    return MockOpenShellClient()


@dataclass
class MockOpenShellClient:
    """
    In-memory mock to exercise Steward governance logic without OpenShell.
    """

    _drafts: Dict[str, DraftPolicy] = field(default_factory=dict)
    _chunks: Dict[str, Dict[str, DraftPolicyChunk]] = field(default_factory=dict)

    def seed_pending_chunk(
        self,
        *,
        sandbox_name: str,
        rule_name: str,
        proposed_rule: Dict[str, Any],
        rationale: str = "",
        security_notes: str = "",
        confidence: float = 0.0,
    ) -> str:
        chunk_id = str(uuid4())
        chunk = DraftPolicyChunk(
            id=chunk_id,
            status="pending",
            rule_name=rule_name,
            proposed_rule=proposed_rule,
            rationale=rationale,
            security_notes=security_notes,
            confidence=confidence,
        )
        self._chunks.setdefault(sandbox_name, {})[chunk_id] = chunk
        self._sync(sandbox_name)
        return chunk_id

    def _sync(self, sandbox_name: str) -> None:
        existing = self._drafts.get(sandbox_name)
        draft_version = (existing.draft_version + 1) if existing else 1
        chunks = list(self._chunks.get(sandbox_name, {}).values())
        self._drafts[sandbox_name] = DraftPolicy(
            sandbox_name=sandbox_name,
            draft_version=draft_version,
            chunks=chunks,
            rolling_summary="",
        )

    def get_draft_policy(self, *, sandbox_name: str, status_filter: str = "") -> DraftPolicy:
        draft = self._drafts.get(sandbox_name)
        if draft is None:
            draft = DraftPolicy(sandbox_name=sandbox_name, draft_version=0, chunks=(), rolling_summary="")
            self._drafts[sandbox_name] = draft
            self._chunks.setdefault(sandbox_name, {})
        if status_filter:
            chunks = [c for c in draft.chunks if c.status == status_filter]
            return DraftPolicy(
                sandbox_name=draft.sandbox_name,
                draft_version=draft.draft_version,
                chunks=chunks,
                rolling_summary=draft.rolling_summary,
            )
        return draft

    def approve_draft_chunk(self, *, sandbox_name: str, chunk_id: str) -> Dict[str, Any]:
        chunk = self._chunks.get(sandbox_name, {}).get(chunk_id)
        if chunk is None:
            return {"ok": False, "error": "chunk_not_found"}
        self._chunks[sandbox_name][chunk_id] = DraftPolicyChunk(**{**chunk.__dict__, "status": "approved"})
        self._sync(sandbox_name)
        return {"ok": True, "policy_version": 1, "policy_hash": "mock"}

    def reject_draft_chunk(self, *, sandbox_name: str, chunk_id: str, reason: str = "") -> Dict[str, Any]:
        chunk = self._chunks.get(sandbox_name, {}).get(chunk_id)
        if chunk is None:
            return {"ok": False, "error": "chunk_not_found"}
        self._chunks[sandbox_name][chunk_id] = DraftPolicyChunk(**{**chunk.__dict__, "status": "rejected"})
        self._sync(sandbox_name)
        return {"ok": True, "reason": reason}

    def edit_draft_chunk(
        self, *, sandbox_name: str, chunk_id: str, proposed_rule: Dict[str, Any]
    ) -> Dict[str, Any]:
        chunk = self._chunks.get(sandbox_name, {}).get(chunk_id)
        if chunk is None:
            return {"ok": False, "error": "chunk_not_found"}
        self._chunks[sandbox_name][chunk_id] = DraftPolicyChunk(
            **{**chunk.__dict__, "proposed_rule": proposed_rule}
        )
        self._sync(sandbox_name)
        return {"ok": True}

    def approve_all_draft_chunks(
        self, *, sandbox_name: str, include_security_flagged: bool = False
    ) -> Dict[str, Any]:
        changed = 0
        for cid, chunk in list(self._chunks.get(sandbox_name, {}).items()):
            if chunk.status != "pending":
                continue
            if chunk.security_notes and not include_security_flagged:
                continue
            self._chunks[sandbox_name][cid] = DraftPolicyChunk(**{**chunk.__dict__, "status": "approved"})
            changed += 1
        self._sync(sandbox_name)
        return {"ok": True, "chunks_approved": changed, "chunks_skipped": 0}

    def clear_draft_chunks(self, *, sandbox_name: str) -> Dict[str, Any]:
        cleared = len(self._chunks.get(sandbox_name, {}))
        self._chunks[sandbox_name] = {}
        self._sync(sandbox_name)
        return {"ok": True, "chunks_cleared": cleared}
