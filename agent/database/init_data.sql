-- ==========================================================
-- 数码电商智能客服 · 模拟数据初始化脚本
-- 作用：创建业务表 + 插入仿真数据（商品/订单/物流/优惠/售后/工单/用量）
-- 用法：mysql -uroot -p digital_shop < init_data.sql
-- 注意：本文件全部为虚构 MOCK 数据，仅用于演示。
-- ==========================================================

-- 1. 商品目录表（给 MCP 商品查询工具用）
CREATE TABLE products (
    product_id VARCHAR(50) PRIMARY KEY,
    name       VARCHAR(100) NOT NULL,
    brand      VARCHAR(50) NOT NULL,
    category   VARCHAR(50) NOT NULL,
    price      DECIMAL(10,2) NOT NULL,
    specs      JSON
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='商品目录表';

-- 2. 订单表
CREATE TABLE orders (
    order_id    VARCHAR(50) PRIMARY KEY,
    user_id     VARCHAR(50) NOT NULL,
    product_name VARCHAR(100) NOT NULL,
    amount      DECIMAL(10,2) NOT NULL,
    status      VARCHAR(20) NOT NULL,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_user (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='订单表';

-- 3. 物流表
CREATE TABLE logistics (
    tracking_no VARCHAR(50) PRIMARY KEY,
    order_id    VARCHAR(50) NOT NULL,
    carrier     VARCHAR(50),
    status      VARCHAR(50),
    updated_at  DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='物流表';

-- 4. 优惠券表
CREATE TABLE coupons (
    coupon_id        VARCHAR(50) PRIMARY KEY,
    name             VARCHAR(100) NOT NULL,
    discount_type    VARCHAR(20) NOT NULL,
    discount_value   DECIMAL(10,2) NOT NULL,
    condition_amount DECIMAL(10,2)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='优惠券表';

-- 5. 售后单表
CREATE TABLE after_sales (
    as_id    VARCHAR(50) PRIMARY KEY,
    order_id VARCHAR(50) NOT NULL,
    user_id  VARCHAR(50) NOT NULL,
    type     VARCHAR(20) NOT NULL,
    status   VARCHAR(20) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='售后单表';

-- 6. 人工转接工单表（状态机：0待处理/1接管中/2取消/3关闭）
CREATE TABLE tickets (
    id              BIGINT PRIMARY KEY AUTO_INCREMENT,
    ticket_no       VARCHAR(32) NOT NULL UNIQUE,
    user_id         VARCHAR(64) NOT NULL,
    session_id      VARCHAR(128) NOT NULL,
    reason          VARCHAR(128) NOT NULL,
    context_summary TEXT,
    status          TINYINT NOT NULL DEFAULT 0,
    priority        TINYINT NOT NULL DEFAULT 0,
    created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    closed_at       DATETIME NULL,
    INDEX idx_status (status),
    INDEX idx_user (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='人工转接工单表';

-- 7. 工单操作日志表
CREATE TABLE ticket_logs (
    id         BIGINT PRIMARY KEY AUTO_INCREMENT,
    ticket_id  BIGINT NOT NULL,
    action     VARCHAR(32) NOT NULL,
    old_status TINYINT NOT NULL,
    new_status TINYINT NOT NULL,
    operator   VARCHAR(64) NOT NULL DEFAULT '',
    remark     VARCHAR(255) DEFAULT '',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_ticket (ticket_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='工单操作日志表';

-- 8. token 用量计费表
CREATE TABLE token_usage (
    id            BIGINT PRIMARY KEY AUTO_INCREMENT,
    user_id       VARCHAR(64) NOT NULL,
    session_id    VARCHAR(128) NOT NULL,
    model         VARCHAR(64) NOT NULL DEFAULT '',
    input_tokens  INT NOT NULL DEFAULT 0,
    output_tokens INT NOT NULL DEFAULT 0,
    total_tokens  INT NOT NULL DEFAULT 0,
    cost          DECIMAL(10,6) NOT NULL DEFAULT 0,
    created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_user (user_id),
    INDEX idx_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='token 用量计费表';

-- ==========================================================
-- 插入 mock 数据
-- ==========================================================

-- 商品（19 款，覆盖手机/笔记本/耳机/平板/智能手表）
INSERT INTO products (product_id, name, brand, category, price, specs) VALUES
('P_IPHONE15PRO','iPhone 15 Pro','Apple','手机',7999.00,'{"内存":"8GB","屏幕":"6.1英寸","存储":"256GB","芯片":"A17 Pro"}'),
('P_IPHONE15','iPhone 15','Apple','手机',5999.00,'{"内存":"6GB","屏幕":"6.1英寸","存储":"128GB","芯片":"A16"}'),
('P_MI14','小米14','小米','手机',4299.00,'{"内存":"12GB","屏幕":"6.36英寸","存储":"256GB","芯片":"骁龙8Gen3"}'),
('P_MI14PRO','小米14 Pro','小米','手机',4999.00,'{"内存":"12GB","屏幕":"6.73英寸","存储":"256GB","芯片":"骁龙8Gen3"}'),
('P_MATE60','华为 Mate 60 Pro','华为','手机',6999.00,'{"内存":"12GB","屏幕":"6.82英寸","存储":"512GB","芯片":"麒麟9000S"}'),
('P_FINDX7','OPPO Find X7','OPPO','手机',3999.00,'{"内存":"12GB","屏幕":"6.78英寸","存储":"256GB","芯片":"天玑9300"}'),
('P_VIVOX100','vivo X100','vivo','手机',3999.00,'{"内存":"12GB","屏幕":"6.78英寸","存储":"256GB","芯片":"天玑9300"}'),
('P_MACBOOK14','MacBook Pro 14','Apple','笔记本',14999.00,'{"内存":"18GB","屏幕":"14.2英寸","存储":"512GB","芯片":"M3 Pro"}'),
('P_MACBOOKAIR','MacBook Air 13','Apple','笔记本',8999.00,'{"内存":"16GB","屏幕":"13.6英寸","存储":"256GB","芯片":"M3"}'),
('P_LENOVO16','联想小新 Pro 16','联想','笔记本',5299.00,'{"内存":"16GB","屏幕":"16英寸","存储":"1TB","芯片":"酷睿Ultra5"}'),
('P_MATEBOOK14','华为 MateBook 14','华为','笔记本',5699.00,'{"内存":"16GB","屏幕":"14英寸","存储":"512GB","芯片":"酷睿Ultra"}'),
('P_AIRPODS','AirPods Pro 2','Apple','耳机',1899.00,'{"降噪":"主动降噪","续航":"30小时","芯片":"H2"}'),
('P_SONYXM5','Sony WH-1000XM5','Sony','耳机',2699.00,'{"降噪":"主动降噪","续航":"30小时"}'),
('P_BOSEQC45','Bose QC45','Bose','耳机',2299.00,'{"降噪":"主动降噪","续航":"24小时"}'),
('P_MIBUDS4','小米 Buds 4 Pro','小米','耳机',999.00,'{"降噪":"48dB降噪","续航":"38小时"}'),
('P_IPADAIR','iPad Air','Apple','平板',4799.00,'{"内存":"8GB","屏幕":"11英寸","存储":"128GB","芯片":"M2"}'),
('P_MIPAD6','小米平板 6 Pro','小米','平板',2499.00,'{"内存":"8GB","屏幕":"11英寸","存储":"256GB","芯片":"骁龙8+"}'),
('P_AWATCH9','Apple Watch Series 9','Apple','智能手表',2999.00,'{"续航":"18小时","屏幕":"全天候"}'),
('P_MIWATCHS3','小米手表 S3','小米','智能手表',799.00,'{"续航":"15天","屏幕":"1.43英寸"}');

-- 订单（5 个用户，21 笔，各种状态）
INSERT INTO orders (order_id, user_id, product_name, amount, status) VALUES
('ORD-1001-001','user_1001','iPhone 15 Pro',7999.00,'Shipped'),
('ORD-1001-002','user_1001','AirPods Pro 2',1899.00,'Completed'),
('ORD-1001-003','user_1001','MacBook Pro 14',14999.00,'Paid'),
('ORD-1001-004','user_1001','小米14',4299.00,'Completed'),
('ORD-1001-005','user_1001','Apple Watch Series 9',2999.00,'Shipped'),
('ORD-1002-001','user_1002','小米14 Pro',4999.00,'Shipped'),
('ORD-1002-002','user_1002','Sony WH-1000XM5',2699.00,'Completed'),
('ORD-1002-003','user_1002','联想小新 Pro 16',5299.00,'Paid'),
('ORD-1002-004','user_1002','iPad Air',4799.00,'Completed'),
('ORD-1003-001','user_1003','华为 Mate 60 Pro',6999.00,'Shipped'),
('ORD-1003-002','user_1003','华为 MateBook 14',5699.00,'Completed'),
('ORD-1003-003','user_1003','Bose QC45',2299.00,'Shipped'),
('ORD-1003-004','user_1003','小米平板 6 Pro',2499.00,'Paid'),
('ORD-1004-001','user_1004','OPPO Find X7',3999.00,'Completed'),
('ORD-1004-002','user_1004','vivo X100',3999.00,'Shipped'),
('ORD-1004-003','user_1004','小米 Buds 4 Pro',999.00,'Completed'),
('ORD-1004-004','user_1004','MacBook Air 13',8999.00,'Paid'),
('ORD-1005-001','user_1005','iPhone 15',5999.00,'Shipped'),
('ORD-1005-002','user_1005','小米手表 S3',799.00,'Completed'),
('ORD-1005-003','user_1005','Sony WH-1000XM5',2699.00,'Paid'),
('ORD-1005-004','user_1005','联想小新 Pro 16',5299.00,'Completed');

-- 物流
INSERT INTO logistics (tracking_no, order_id, carrier, status) VALUES
('SF1001001','ORD-1001-001','顺丰速运','运输中'),
('YT1001002','ORD-1001-002','圆通快递','已签收'),
('SF1001003','ORD-1001-003','顺丰速运','已揽收'),
('ZT1001004','ORD-1001-004','中通快递','已签收'),
('SF1001005','ORD-1001-005','顺丰速运','运输中'),
('YT1002001','ORD-1002-001','圆通快递','运输中'),
('SF1002002','ORD-1002-002','顺丰速运','已签收'),
('YD1002003','ORD-1002-003','韵达快递','已揽收'),
('ZT1002004','ORD-1002-004','中通快递','已签收'),
('SF1003001','ORD-1003-001','顺丰速运','运输中'),
('YT1003002','ORD-1003-002','圆通快递','已签收'),
('SF1003003','ORD-1003-003','顺丰速运','运输中'),
('YD1003004','ORD-1003-004','韵达快递','已揽收'),
('ZT1004001','ORD-1004-001','中通快递','已签收'),
('SF1004002','ORD-1004-002','顺丰速运','运输中'),
('YT1004003','ORD-1004-003','圆通快递','已签收'),
('SF1004004','ORD-1004-004','顺丰速运','已揽收'),
('ZT1005001','ORD-1005-001','中通快递','运输中'),
('YT1005002','ORD-1005-002','圆通快递','已签收'),
('SF1005003','ORD-1005-003','顺丰速运','已揽收'),
('YD1005004','ORD-1005-004','韵达快递','已签收');

-- 优惠券
INSERT INTO coupons (coupon_id, name, discount_type, discount_value, condition_amount) VALUES
('CPN-100','满1000减100','full_reduction',100.00,1000.00),
('CPN-200','全场9折','discount',0.90,NULL),
('CPN-300','满5000减500','full_reduction',500.00,5000.00),
('CPN-400','新人满99减20','full_reduction',20.00,99.00),
('CPN-500','数码品类95折','discount',0.95,NULL),
('CPN-600','满2000减200','full_reduction',200.00,2000.00);

-- 售后单
INSERT INTO after_sales (as_id, order_id, user_id, type, status) VALUES
('AS-1001','ORD-1001-002','user_1001','refund','processing'),
('AS-1002','ORD-1002-001','user_1002','exchange','pending'),
('AS-1003','ORD-1003-001','user_1003','repair','processing'),
('AS-1004','ORD-1004-001','user_1004','refund','done'),
('AS-1005','ORD-1005-001','user_1005','exchange','processing'),
('AS-1006','ORD-1001-001','user_1001','repair','pending'),
('AS-1007','ORD-1002-002','user_1002','refund','done'),
('AS-1008','ORD-1003-003','user_1003','exchange','done'),
('AS-1009','ORD-1004-002','user_1004','repair','processing'),
('AS-1010','ORD-1005-003','user_1005','refund','pending');
