"""
多格式文档入库：加载 → 清洗 → 父子分块 → 分批向量化 → 增量入库（Milvus HNSW）。
用法：
  .venv/Scripts/python.exe scripts/ingest_vector.py            # 增量（按 doc_id 幂等 upsert）
  .venv/Scripts/python.exe scripts/ingest_vector.py --reset    # 全量重置（drop 集合后重灌）
"""
import argparse
import os
import sys
from pathlib import Path

# 把 agent 目录加进 sys.path
AGENT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "agent")
sys.path.insert(0, AGENT_DIR)

from dotenv import load_dotenv
load_dotenv(os.path.join(AGENT_DIR, ".env"))

from core.rag import load_document, list_supported_files, clean_text, chunk_document, COLLECTION_NAME
from core.rag.indexer import VectorIndexer


def ingest(directory: str = "demo_data", reset: bool = False) -> None:
    indexer = VectorIndexer()
    indexer.ensure_collection()

    if reset:
        client = indexer._ensure_client()
        if client.has_collection(COLLECTION_NAME):
            client.drop_collection(COLLECTION_NAME)
        indexer.ensure_collection()
        print("♻️  已重置集合（全量重灌）")

    files = list_supported_files(directory)
    total = 0
    for f in files:
        text = clean_text(load_document(f))
        chunks = chunk_document(text)
        n = indexer.index_document(f.name, f.name, chunks)
        total += n
        print(f"✅ {f.name}: {n} 个 chunk")
    print(f"\n✅ 入库完成：{len(files)} 份文档，共 {total} 个 chunk")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="多格式文档向量入库")
    parser.add_argument("--dir", default="demo_data", help="文档目录（默认 demo_data）")
    parser.add_argument("--reset", action="store_true", help="全量重置（drop 集合后重灌）")
    args = parser.parse_args()
    ingest(args.dir, args.reset)
