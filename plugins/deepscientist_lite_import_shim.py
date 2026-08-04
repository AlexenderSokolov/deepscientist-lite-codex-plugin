"""Import helpers for the hyphenated plugin source directory used by tests."""
from __future__ import annotations

import importlib.util
from pathlib import Path

_PATH = Path(__file__).parent / "deepscientist-lite-core" / "scripts" / "ds_lite_loop.py"
_SPEC = importlib.util.spec_from_file_location("ds_lite_loop", _PATH)
if _SPEC is None or _SPEC.loader is None:
    raise ImportError("cannot load ds_lite_loop")
ds_lite_loop = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(ds_lite_loop)

_AUTONOMY_PATH = Path(__file__).parent / "deepscientist-lite-core" / "scripts" / "ds_lite_autonomy.py"
_RECOVERY_PATH = Path(__file__).parent / "deepscientist-lite-core" / "scripts" / "ds_lite_recovery.py"
_RECOVERY_SPEC = importlib.util.spec_from_file_location("ds_lite_recovery", _RECOVERY_PATH)
if _RECOVERY_SPEC is None or _RECOVERY_SPEC.loader is None:
    raise ImportError("cannot load ds_lite_recovery")
ds_lite_recovery = importlib.util.module_from_spec(_RECOVERY_SPEC)
import sys
sys.modules["ds_lite_recovery"] = ds_lite_recovery
_RECOVERY_SPEC.loader.exec_module(ds_lite_recovery)
_AUTONOMY_SPEC = importlib.util.spec_from_file_location("ds_lite_autonomy", _AUTONOMY_PATH)
if _AUTONOMY_SPEC is None or _AUTONOMY_SPEC.loader is None:
    raise ImportError("cannot load ds_lite_autonomy")
ds_lite_autonomy = importlib.util.module_from_spec(_AUTONOMY_SPEC)
_AUTONOMY_SPEC.loader.exec_module(ds_lite_autonomy)

_AUTORESEARCH_PATH = Path(__file__).parent / "deepscientist-lite-core" / "scripts" / "ds_lite_autoresearch_runner.py"
_AUTORESEARCH_SPEC = importlib.util.spec_from_file_location("ds_lite_autoresearch_runner", _AUTORESEARCH_PATH)
if _AUTORESEARCH_SPEC is None or _AUTORESEARCH_SPEC.loader is None:
    raise ImportError("cannot load ds_lite_autoresearch_runner")
ds_lite_autoresearch_runner = importlib.util.module_from_spec(_AUTORESEARCH_SPEC)
_AUTORESEARCH_SPEC.loader.exec_module(ds_lite_autoresearch_runner)

_SIGNAL_LEDGER_PATH = Path(__file__).parent / "deepscientist-lite-core" / "scripts" / "ds_lite_signal_ledger.py"
_SIGNAL_LEDGER_SPEC = importlib.util.spec_from_file_location("ds_lite_signal_ledger", _SIGNAL_LEDGER_PATH)
if _SIGNAL_LEDGER_SPEC is None or _SIGNAL_LEDGER_SPEC.loader is None:
    raise ImportError("cannot load ds_lite_signal_ledger")
ds_lite_signal_ledger = importlib.util.module_from_spec(_SIGNAL_LEDGER_SPEC)
_SIGNAL_LEDGER_SPEC.loader.exec_module(ds_lite_signal_ledger)

_FRONTIER_PATH = Path(__file__).parent / "deepscientist-lite-core" / "scripts" / "ds_lite_frontier.py"
_FRONTIER_SPEC = importlib.util.spec_from_file_location("ds_lite_frontier", _FRONTIER_PATH)
if _FRONTIER_SPEC is None or _FRONTIER_SPEC.loader is None:
    raise ImportError("cannot load ds_lite_frontier")
ds_lite_frontier = importlib.util.module_from_spec(_FRONTIER_SPEC)
_FRONTIER_SPEC.loader.exec_module(ds_lite_frontier)

_CLAIM_LEDGER_PATH = Path(__file__).parent / "deepscientist-lite-core" / "scripts" / "ds_lite_claim_ledger.py"
_CLAIM_LEDGER_SPEC = importlib.util.spec_from_file_location("ds_lite_claim_ledger", _CLAIM_LEDGER_PATH)
if _CLAIM_LEDGER_SPEC is None or _CLAIM_LEDGER_SPEC.loader is None:
    raise ImportError("cannot load ds_lite_claim_ledger")
ds_lite_claim_ledger = importlib.util.module_from_spec(_CLAIM_LEDGER_SPEC)
_CLAIM_LEDGER_SPEC.loader.exec_module(ds_lite_claim_ledger)

_FACTOR_CARD_V2_PATH = Path(__file__).parent / "deepscientist-lite-core" / "scripts" / "ds_lite_factor_card_v2.py"
_FACTOR_CARD_V2_SPEC = importlib.util.spec_from_file_location("ds_lite_factor_card_v2", _FACTOR_CARD_V2_PATH)
if _FACTOR_CARD_V2_SPEC is None or _FACTOR_CARD_V2_SPEC.loader is None:
    raise ImportError("cannot load ds_lite_factor_card_v2")
ds_lite_factor_card_v2 = importlib.util.module_from_spec(_FACTOR_CARD_V2_SPEC)
_FACTOR_CARD_V2_SPEC.loader.exec_module(ds_lite_factor_card_v2)

_ASSESSMENT_PATH = Path(__file__).parent / "deepscientist-lite-core" / "scripts" / "ds_lite_assessment.py"
_ASSESSMENT_SPEC = importlib.util.spec_from_file_location("ds_lite_assessment", _ASSESSMENT_PATH)
if _ASSESSMENT_SPEC is None or _ASSESSMENT_SPEC.loader is None:
    raise ImportError("cannot load ds_lite_assessment")
ds_lite_assessment = importlib.util.module_from_spec(_ASSESSMENT_SPEC)
_ASSESSMENT_SPEC.loader.exec_module(ds_lite_assessment)

_CONTRACT_V2_PATH = Path(__file__).parent / "deepscientist-lite-core" / "scripts" / "ds_lite_contract_v2.py"
_CONTRACT_V2_SPEC = importlib.util.spec_from_file_location("ds_lite_contract_v2", _CONTRACT_V2_PATH)
if _CONTRACT_V2_SPEC is None or _CONTRACT_V2_SPEC.loader is None:
    raise ImportError("cannot load ds_lite_contract_v2")
ds_lite_contract_v2 = importlib.util.module_from_spec(_CONTRACT_V2_SPEC)
_CONTRACT_V2_SPEC.loader.exec_module(ds_lite_contract_v2)
_CLAIM_CHAIN_PATH = Path(__file__).parent / "deepscientist-lite-core" / "scripts" / "ds_lite_claim_chain.py"
_CLAIM_CHAIN_SPEC = importlib.util.spec_from_file_location("ds_lite_claim_chain", _CLAIM_CHAIN_PATH)
if _CLAIM_CHAIN_SPEC is None or _CLAIM_CHAIN_SPEC.loader is None:
    raise ImportError("cannot load ds_lite_claim_chain")
ds_lite_claim_chain = importlib.util.module_from_spec(_CLAIM_CHAIN_SPEC)
_CLAIM_CHAIN_SPEC.loader.exec_module(ds_lite_claim_chain)
_HANDOFF_QUALITY_PATH = Path(__file__).parent / "deepscientist-lite-core" / "scripts" / "ds_lite_handoff_quality.py"
_HANDOFF_QUALITY_SPEC = importlib.util.spec_from_file_location("ds_lite_handoff_quality", _HANDOFF_QUALITY_PATH)
if _HANDOFF_QUALITY_SPEC is None or _HANDOFF_QUALITY_SPEC.loader is None:
    raise ImportError("cannot load ds_lite_handoff_quality")
ds_lite_handoff_quality = importlib.util.module_from_spec(_HANDOFF_QUALITY_SPEC)
_HANDOFF_QUALITY_SPEC.loader.exec_module(ds_lite_handoff_quality)
_CATALOG_PATH = Path(__file__).parent / "deepscientist-lite-core" / "scripts" / "ds_lite_catalog.py"
_CATALOG_SPEC = importlib.util.spec_from_file_location("ds_lite_catalog", _CATALOG_PATH)
if _CATALOG_SPEC is None or _CATALOG_SPEC.loader is None:
    raise ImportError("cannot load ds_lite_catalog")
ds_lite_catalog = importlib.util.module_from_spec(_CATALOG_SPEC)
_CATALOG_SPEC.loader.exec_module(ds_lite_catalog)

_EXPERIENCE_LEDGER_PATH = Path(__file__).parent / "deepscientist-lite-core" / "scripts" / "ds_lite_experience_ledger.py"
_EXPERIENCE_LEDGER_SPEC = importlib.util.spec_from_file_location("ds_lite_experience_ledger", _EXPERIENCE_LEDGER_PATH)
if _EXPERIENCE_LEDGER_SPEC is None or _EXPERIENCE_LEDGER_SPEC.loader is None:
    raise ImportError("cannot load ds_lite_experience_ledger")
ds_lite_experience_ledger = importlib.util.module_from_spec(_EXPERIENCE_LEDGER_SPEC)
_EXPERIENCE_LEDGER_SPEC.loader.exec_module(ds_lite_experience_ledger)

_SKILL_ADMISSION_PATH = Path(__file__).parent / "deepscientist-lite-core" / "scripts" / "ds_lite_skill_admission.py"
_SKILL_ADMISSION_SPEC = importlib.util.spec_from_file_location("ds_lite_skill_admission", _SKILL_ADMISSION_PATH)
if _SKILL_ADMISSION_SPEC is None or _SKILL_ADMISSION_SPEC.loader is None:
    raise ImportError("cannot load ds_lite_skill_admission")
ds_lite_skill_admission = importlib.util.module_from_spec(_SKILL_ADMISSION_SPEC)
_SKILL_ADMISSION_SPEC.loader.exec_module(ds_lite_skill_admission)
_CAUSAL_ROUTER_PATH = Path(__file__).parent / "deepscientist-lite-core" / "scripts" / "ds_lite_causal_router.py"
_CAUSAL_ROUTER_SPEC = importlib.util.spec_from_file_location("ds_lite_causal_router", _CAUSAL_ROUTER_PATH)
if _CAUSAL_ROUTER_SPEC is None or _CAUSAL_ROUTER_SPEC.loader is None:
    raise ImportError("cannot load ds_lite_causal_router")
ds_lite_causal_router = importlib.util.module_from_spec(_CAUSAL_ROUTER_SPEC)
_CAUSAL_ROUTER_SPEC.loader.exec_module(ds_lite_causal_router)
_OPENSCIENCE_BRIDGE_PATH = Path(__file__).parent / "deepscientist-lite-core" / "scripts" / "ds_lite_openscience_bridge.py"
_OPENSCIENCE_BRIDGE_SPEC = importlib.util.spec_from_file_location("ds_lite_openscience_bridge", _OPENSCIENCE_BRIDGE_PATH)
if _OPENSCIENCE_BRIDGE_SPEC is None or _OPENSCIENCE_BRIDGE_SPEC.loader is None:
    raise ImportError("cannot load ds_lite_openscience_bridge")
ds_lite_openscience_bridge = importlib.util.module_from_spec(_OPENSCIENCE_BRIDGE_SPEC)
_OPENSCIENCE_BRIDGE_SPEC.loader.exec_module(ds_lite_openscience_bridge)
_V6_EVALUATION_PATH = Path(__file__).parent / "deepscientist-lite-core" / "scripts" / "ds_lite_v6_evaluation.py"
_V6_EVALUATION_SPEC = importlib.util.spec_from_file_location("ds_lite_v6_evaluation", _V6_EVALUATION_PATH)
if _V6_EVALUATION_SPEC is None or _V6_EVALUATION_SPEC.loader is None:
    raise ImportError("cannot load ds_lite_v6_evaluation")
ds_lite_v6_evaluation = importlib.util.module_from_spec(_V6_EVALUATION_SPEC)
_V6_EVALUATION_SPEC.loader.exec_module(ds_lite_v6_evaluation)