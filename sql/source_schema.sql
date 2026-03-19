-- Source database schema
-- Column was renamed from total_price to grand_total (this breaks the ETL)
CREATE TABLE sales (
    id          INT           PRIMARY KEY IDENTITY,
    product_name NVARCHAR(100) NOT NULL,
    grand_total  DECIMAL(10,2) NOT NULL,
    sale_date    DATE          NOT NULL
);
