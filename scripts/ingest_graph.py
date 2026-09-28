"""
知识图谱入库脚本：把品牌/品类/商品实体 + 关系写入 Neo4j。
运行前确保 Neo4j 已启动。
用法：在项目根目录运行  .venv/Scripts/python.exe scripts/ingest_graph.py
"""
import os
from dotenv import load_dotenv
from neo4j import GraphDatabase

load_dotenv('agent/.env')

uri = os.getenv('NEO4J_URI', 'bolt://127.0.0.1:7687')
user = os.getenv('NEO4J_USER', 'neo4j')
password = os.getenv('NEO4J_PASSWORD', 'cloudagent123')

driver = GraphDatabase.driver(uri, auth=(user, password))

brands = [
    {"id": "apple", "name": "Apple", "country": "美国"},
    {"id": "xiaomi", "name": "小米", "country": "中国"},
    {"id": "huawei", "name": "华为", "country": "中国"},
    {"id": "oppo", "name": "OPPO", "country": "中国"},
    {"id": "vivo", "name": "vivo", "country": "中国"},
    {"id": "sony", "name": "Sony", "country": "日本"},
    {"id": "bose", "name": "Bose", "country": "美国"},
    {"id": "lenovo", "name": "联想", "country": "中国"},
]
categories = [
    {"id": "phone", "name": "手机"},
    {"id": "laptop", "name": "笔记本"},
    {"id": "earphone", "name": "耳机"},
    {"id": "tablet", "name": "平板"},
    {"id": "watch", "name": "智能手表"},
]
# 每种商品用 props 存自己的属性（不同品类属性不同）
products = [
    {"id": "iphone-15-pro", "name": "iPhone 15 Pro", "brand_id": "apple", "category_id": "phone",
     "props": {"price": 7999.0, "ram": "8GB", "screen": "6.1英寸", "chip": "A17 Pro"}},
    {"id": "iphone-15", "name": "iPhone 15", "brand_id": "apple", "category_id": "phone",
     "props": {"price": 5999.0, "ram": "6GB", "screen": "6.1英寸", "chip": "A16"}},
    {"id": "xiaomi-14", "name": "小米14", "brand_id": "xiaomi", "category_id": "phone",
     "props": {"price": 4299.0, "ram": "12GB", "screen": "6.36英寸", "chip": "骁龙8Gen3"}},
    {"id": "xiaomi-14-pro", "name": "小米14 Pro", "brand_id": "xiaomi", "category_id": "phone",
     "props": {"price": 4999.0, "ram": "12GB", "screen": "6.73英寸", "chip": "骁龙8Gen3"}},
    {"id": "huawei-mate60-pro", "name": "华为 Mate 60 Pro", "brand_id": "huawei", "category_id": "phone",
     "props": {"price": 6999.0, "ram": "12GB", "screen": "6.82英寸", "chip": "麒麟9000S"}},
    {"id": "oppo-find-x7", "name": "OPPO Find X7", "brand_id": "oppo", "category_id": "phone",
     "props": {"price": 3999.0, "ram": "12GB", "screen": "6.78英寸", "chip": "天玑9300"}},
    {"id": "vivo-x100", "name": "vivo X100", "brand_id": "vivo", "category_id": "phone",
     "props": {"price": 3999.0, "ram": "12GB", "screen": "6.78英寸", "chip": "天玑9300"}},
    {"id": "macbook-pro-14", "name": "MacBook Pro 14", "brand_id": "apple", "category_id": "laptop",
     "props": {"price": 14999.0, "ram": "18GB", "screen": "14.2英寸", "chip": "M3 Pro"}},
    {"id": "macbook-air-13", "name": "MacBook Air 13", "brand_id": "apple", "category_id": "laptop",
     "props": {"price": 8999.0, "ram": "16GB", "screen": "13.6英寸", "chip": "M3"}},
    {"id": "lenovo-xiaoxin-16", "name": "联想小新 Pro 16", "brand_id": "lenovo", "category_id": "laptop",
     "props": {"price": 5299.0, "ram": "16GB", "screen": "16英寸", "chip": "酷睿Ultra5"}},
    {"id": "huawei-matebook-14", "name": "华为 MateBook 14", "brand_id": "huawei", "category_id": "laptop",
     "props": {"price": 5699.0, "ram": "16GB", "screen": "14英寸", "chip": "酷睿Ultra"}},
    {"id": "airpods-pro-2", "name": "AirPods Pro 2", "brand_id": "apple", "category_id": "earphone",
     "props": {"price": 1899.0, "anc": "主动降噪", "battery": "30小时"}},
    {"id": "sony-wh1000xm5", "name": "Sony WH-1000XM5", "brand_id": "sony", "category_id": "earphone",
     "props": {"price": 2699.0, "anc": "主动降噪", "battery": "30小时"}},
    {"id": "bose-qc45", "name": "Bose QC45", "brand_id": "bose", "category_id": "earphone",
     "props": {"price": 2299.0, "anc": "主动降噪", "battery": "24小时"}},
    {"id": "xiaomi-buds-4-pro", "name": "小米 Buds 4 Pro", "brand_id": "xiaomi", "category_id": "earphone",
     "props": {"price": 999.0, "anc": "48dB降噪", "battery": "38小时"}},
    {"id": "ipad-air", "name": "iPad Air", "brand_id": "apple", "category_id": "tablet",
     "props": {"price": 4799.0, "ram": "8GB", "screen": "11英寸", "chip": "M2"}},
    {"id": "xiaomi-pad-6-pro", "name": "小米平板 6 Pro", "brand_id": "xiaomi", "category_id": "tablet",
     "props": {"price": 2499.0, "ram": "8GB", "screen": "11英寸", "chip": "骁龙8+"}},
    {"id": "apple-watch-9", "name": "Apple Watch Series 9", "brand_id": "apple", "category_id": "watch",
     "props": {"price": 2999.0, "battery": "18小时"}},
    {"id": "xiaomi-watch-s3", "name": "小米手表 S3", "brand_id": "xiaomi", "category_id": "watch",
     "props": {"price": 799.0, "battery": "15天"}},
]

with driver.session() as session:
    for b in brands:
        session.run("MERGE (n:Brand {id: $id}) SET n.name = $name, n.country = $country", **b)
    for c in categories:
        session.run("MERGE (n:Category {id: $id}) SET n.name = $name", **c)
    for p in products:
        session.run(
            "MERGE (n:Product {id: $id}) SET n.name = $name, n += $props "
            "WITH n MATCH (b:Brand {id: $brand_id}) MERGE (n)-[:BELONGS_TO]->(b) "
            "WITH n MATCH (c:Category {id: $category_id}) MERGE (n)-[:BELONGS_TO]->(c)",
            id=p["id"], name=p["name"], brand_id=p["brand_id"], category_id=p["category_id"], props=p["props"],
        )
    result = session.run("MATCH (n) RETURN count(n) AS cnt").single()
    print(f'✅ 图谱导入完成，节点总数: {result["cnt"]}')

driver.close()
