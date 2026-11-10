-- Esquema de la base de datos de MercaNova.
-- Refleja las 8 hojas del Excel de la cátedra, con claves primarias y foráneas
-- reales. Los CHECK documentan los invariantes verificados sobre el dataset.
-- Se aplica con backend.db.create_schema() y es idempotente (IF NOT EXISTS).

-- Marcas (hoja Brands, 20 filas).
CREATE TABLE IF NOT EXISTS brands (
    brand_id          TEXT PRIMARY KEY,
    brand_name        TEXT NOT NULL,
    country_of_origin TEXT,
    positioning       TEXT
);

-- Categorías (hoja Categories, 37 filas).
-- La clave primaria es subcategory_id: category_id se repite, porque cada fila
-- es un par categoría/subcategoría. Hay 12 categorías y 37 pares, con 37
-- subcategory_id, pero solo 32 nombres de subcategoría distintos: 'Gaming'
-- aparece en 3 categorías, y 'Professional', 'Ergonomic' y 'Standard' en 2 cada
-- una. Por eso products referencia el par (category_name, subcategory_name) con
-- una clave foránea compuesta: el nombre de la subcategoría solo no identifica
-- una fila.
CREATE TABLE IF NOT EXISTS categories (
    subcategory_id   TEXT PRIMARY KEY,
    category_id      TEXT NOT NULL,
    category_name    TEXT NOT NULL,
    subcategory_name TEXT NOT NULL,
    department       TEXT,
    sort_order       INTEGER,
    -- Los nombres son lo que trae Products, así que el par tiene que ser único
    -- para poder referenciarlo desde ahí.
    UNIQUE (category_name, subcategory_name)
);

-- Depósitos (hoja Warehouses, 5 filas).
CREATE TABLE IF NOT EXISTS warehouses (
    warehouse_id     TEXT PRIMARY KEY,
    warehouse_name   TEXT NOT NULL,
    city             TEXT,
    department       TEXT,
    country          TEXT,
    pickup_enabled   INTEGER NOT NULL CHECK (pickup_enabled IN (0, 1)),
    shipping_enabled INTEGER NOT NULL CHECK (shipping_enabled IN (0, 1))
);

-- Productos (hoja Products, 360 filas).
CREATE TABLE IF NOT EXISTS products (
    product_id          TEXT PRIMARY KEY,
    sku                 TEXT NOT NULL UNIQUE,
    name                TEXT NOT NULL,
    brand               TEXT NOT NULL,
    brand_id            TEXT NOT NULL,
    category            TEXT NOT NULL,
    subcategory         TEXT NOT NULL,
    short_description   TEXT,
    description         TEXT,
    recommended_for     TEXT,
    not_recommended_for TEXT,
    key_features        TEXT,
    tags                TEXT,
    color               TEXT,
    weight_kg           REAL CHECK (weight_kg > 0),
    width_cm            REAL CHECK (width_cm > 0),
    height_cm           REAL CHECK (height_cm > 0),
    depth_cm            REAL CHECK (depth_cm > 0),
    warranty_months     INTEGER CHECK (warranty_months >= 0),
    return_days         INTEGER CHECK (return_days >= 0),
    rating              REAL CHECK (rating BETWEEN 0 AND 5),
    review_count        INTEGER CHECK (review_count >= 0),
    launch_date         TEXT,
    active              INTEGER NOT NULL CHECK (active IN (0, 1)),
    image_url           TEXT,
    FOREIGN KEY (brand_id) REFERENCES brands (brand_id),
    FOREIGN KEY (category, subcategory)
        REFERENCES categories (category_name, subcategory_name)
);

-- Especificaciones técnicas (hoja Specifications, 3000 filas).
-- Cada fila trae el valor en value_text o en value_number, nunca en las dos ni
-- en ninguna: 1920 de texto y 1080 numéricas sobre las 3000 filas del dataset.
-- Ojo con los 37 atributos cuyo value_text es el texto literal "None" (por
-- ejemplo "Water Resistance: None"): es un valor del catálogo y significa que
-- el producto no tiene esa característica, no que falte el dato. Son cosas
-- distintas para el asistente, así que la carga lo guarda tal cual.
CREATE TABLE IF NOT EXISTS specifications (
    product_id      TEXT NOT NULL,
    attribute_group TEXT NOT NULL,
    attribute_name  TEXT NOT NULL,
    value_text      TEXT,
    value_number    REAL,
    unit            TEXT,
    PRIMARY KEY (product_id, attribute_group, attribute_name),
    -- Exactamente una de las dos columnas de valor tiene dato.
    CHECK ((value_text IS NULL) <> (value_number IS NULL)),
    FOREIGN KEY (product_id) REFERENCES products (product_id)
);

-- Precios (hoja Pricing, 360 filas: uno por producto).
CREATE TABLE IF NOT EXISTS pricing (
    product_id       TEXT PRIMARY KEY,
    currency         TEXT NOT NULL,
    list_price       REAL NOT NULL CHECK (list_price >= 0),
    current_price    REAL NOT NULL CHECK (current_price >= 0),
    discount_percent INTEGER NOT NULL CHECK (discount_percent BETWEEN 0 AND 100),
    tax_included     INTEGER NOT NULL CHECK (tax_included IN (0, 1)),
    price_updated_at TEXT,
    CHECK (current_price <= list_price),
    FOREIGN KEY (product_id) REFERENCES products (product_id)
);

-- Inventario por depósito (hoja Inventory, 1800 filas = 360 x 5).
CREATE TABLE IF NOT EXISTS inventory (
    product_id           TEXT NOT NULL,
    warehouse_id         TEXT NOT NULL,
    on_hand_qty          INTEGER NOT NULL CHECK (on_hand_qty >= 0),
    reserved_qty         INTEGER NOT NULL CHECK (reserved_qty >= 0),
    available_qty        INTEGER NOT NULL CHECK (available_qty >= 0),
    inventory_status     TEXT NOT NULL,
    inventory_updated_at TEXT,
    PRIMARY KEY (product_id, warehouse_id),
    CHECK (available_qty = on_hand_qty - reserved_qty),
    FOREIGN KEY (product_id) REFERENCES products (product_id),
    FOREIGN KEY (warehouse_id) REFERENCES warehouses (warehouse_id)
);

-- Relaciones entre productos (hoja Relations, 1080 filas).
CREATE TABLE IF NOT EXISTS relations (
    product_id         TEXT NOT NULL,
    related_product_id TEXT NOT NULL,
    relation_type      TEXT NOT NULL
        CHECK (relation_type IN ('alternative_to', 'accessory_for', 'often_bought_with')),
    strength           REAL NOT NULL CHECK (strength BETWEEN 0 AND 1),
    PRIMARY KEY (product_id, related_product_id, relation_type),
    CHECK (product_id <> related_product_id),
    FOREIGN KEY (product_id) REFERENCES products (product_id),
    FOREIGN KEY (related_product_id) REFERENCES products (product_id)
);

-- Órdenes confirmadas (RF-14). **Dato operativo del equipo**: no sale del Excel
-- de la cátedra, lo genera la aplicación cuando el usuario confirma la compra.
-- Se guarda en la base y no en memoria porque la confirmación también descuenta
-- stock de inventory: las dos cosas pasan en la misma transacción, así no queda
-- stock descontado sin orden ni orden sin stock descontado.
CREATE TABLE IF NOT EXISTS orders (
    order_id         TEXT PRIMARY KEY,
    session_id       TEXT NOT NULL,
    created_at       TEXT NOT NULL,
    customer_name    TEXT NOT NULL,
    shipping_address TEXT NOT NULL,
    currency         TEXT NOT NULL,
    total_amount     REAL NOT NULL CHECK (total_amount >= 0)
);

-- Líneas de una orden (RF-14). Guardan el nombre y el precio **al momento de la
-- compra**: si después cambia el catálogo, la orden sigue diciendo lo que el
-- usuario confirmó. Por eso name y unit_price se copian y no se leen con un join.
CREATE TABLE IF NOT EXISTS order_items (
    order_id   TEXT NOT NULL,
    product_id TEXT NOT NULL,
    name       TEXT NOT NULL,
    quantity   INTEGER NOT NULL CHECK (quantity > 0),
    unit_price REAL NOT NULL CHECK (unit_price >= 0),
    currency   TEXT NOT NULL,
    line_total REAL NOT NULL CHECK (line_total >= 0),
    PRIMARY KEY (order_id, product_id),
    FOREIGN KEY (order_id) REFERENCES orders (order_id),
    FOREIGN KEY (product_id) REFERENCES products (product_id)
);

-- Índices para las búsquedas que hacen las tools del asistente.
CREATE INDEX IF NOT EXISTS idx_products_category ON products (category, subcategory);
CREATE INDEX IF NOT EXISTS idx_products_brand ON products (brand_id);
CREATE INDEX IF NOT EXISTS idx_specifications_product ON specifications (product_id);
CREATE INDEX IF NOT EXISTS idx_inventory_product ON inventory (product_id);
CREATE INDEX IF NOT EXISTS idx_relations_product ON relations (product_id, relation_type);

-- El historial de órdenes se consulta por sesión, de la más nueva a la más vieja.
CREATE INDEX IF NOT EXISTS idx_orders_session ON orders (session_id, created_at DESC);
