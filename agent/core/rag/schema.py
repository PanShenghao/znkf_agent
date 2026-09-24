"""RAG 管道共享常量（入库与查询共用，保证分块一致）。"""

COLLECTION_NAME = "product_docs"
EMBEDDING_DIM = 1536

# 父子分块参数
PARENT_SIZE = 600     # parent 块大小（字符），用于生成上下文
CHILD_SIZE = 200      # child 块大小（字符），用于检索
CHILD_OVERLAP = 40    # child 块重叠

BATCH_SIZE = 100      # 向量化分批大小（防 OOM）
