"""Página: validação/qualidade (manifests × arquivos, stubs, buracos).

Lê o sistema de arquivos (bronze + manifests), não o warehouse.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st

import app.audit as audit
import app.theme as theme

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"

theme.page_config(title="Rocket League Analyzer — Validação", icon="🔍")
theme.apply()
theme.header("Validação / qualidade dos dados")


@st.cache_data(ttl=300, show_spinner="Auditando manifests × arquivos...")
def _audit(data_dir: str):
    return audit.audit(data_dir)


@st.cache_data(ttl=300, show_spinner="Procurando stubs...")
def _stubs(data_dir: str, deep: bool):
    return audit.detect_stubs(data_dir, deep=deep)


with st.sidebar:
    st.caption("Auditoria (bronze/manifests)")
    if st.button("🔄 Re-scan"):
        st.cache_data.clear()

df = _audit(str(DATA_DIR))

c1, c2, c3, c4 = st.columns(4)
c1.metric("Buckets", f"{len(df):,}")
c2.metric("Buckets com pendentes", f"{(df['pending'] > 0).sum():,}")
c3.metric("Replays pendentes", f"{int(df['pending'].sum()):,}")
c4.metric("Órfãos", f"{int(df['orphans'].sum()):,}")

st.divider()
st.subheader("Consistência manifest × arquivos")
st.dataframe(df, width="stretch", hide_index=True)

holes = df[df["pending"] > 0]
st.divider()
st.subheader(f"⚠️ Buckets com pendências ({len(holes)})")
if len(holes):
    st.dataframe(holes, width="stretch", hide_index=True)
else:
    st.success("Nenhuma pendência: todos os IDs dos manifests têm arquivo.")

st.divider()
st.subheader("Stubs / arquivos suspeitos")
deep = st.checkbox("Validar conteúdo JSON (mais lento)", value=False)
stubs = _stubs(str(DATA_DIR), deep)
if len(stubs):
    st.warning(f"{len(stubs)} arquivos suspeitos")
    st.dataframe(stubs, width="stretch", hide_index=True)
else:
    st.success("Nenhum arquivo suspeito encontrado.")
