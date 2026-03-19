-- Target database schema
-- Still expects the old column name total_price
CREATE TABLE sales (
    id           INT           PRIMARY KEY IDENTITY,
    product_name NVARCHAR(100) NOT NULL,
    total_price  DECIMAL(10,2) NOT NULL,
    sale_date    DATE          NOT NULL
);
