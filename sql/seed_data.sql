-- Seed data for source database (uses grand_total column)
-- Run against the source DB after creating the schema

INSERT INTO sales (product_name, grand_total, sale_date) VALUES
('Laptop Pro 15"',             1299.99, '2024-01-15'),
('Wireless Noise-Cancel Headphones', 249.99, '2024-01-16'),
('USB-C Hub 7-Port',            79.99,  '2024-01-17'),
('Mechanical Keyboard RGB',    189.99,  '2024-01-18'),
('4K IPS Monitor 27"',         599.99,  '2024-01-19'),
('Ergonomic Vertical Mouse',    89.99,  '2024-01-20'),
('Anti-Fatigue Standing Mat',   49.99,  '2024-01-21'),
('Webcam 1080p Auto-Focus',    129.99,  '2024-01-22'),
('Portable SSD 1TB USB-C',     149.99,  '2024-01-23'),
('Smart Speaker Wifi',          99.99,  '2024-01-24'),
('Android Tablet 10.4"',       449.99,  '2024-01-25'),
('Adjustable Phone/Tablet Stand', 29.99, '2024-01-26'),
('Cable Management Kit 50pc',   19.99,  '2024-01-27'),
('LED Desk Lamp USB-Charged',   69.99,  '2024-01-28'),
('Power Bank 20000mAh 65W',     59.99,  '2024-01-29'),
('True Wireless ANC Earbuds',  199.99,  '2024-01-30'),
('Pro Gaming Controller',       79.99,  '2024-01-31'),
('Privacy Screen Filter 14"',   39.99,  '2024-02-01'),
('Waterproof Laptop Backpack',  89.99,  '2024-02-02'),
('Bluetooth Compact Numpad',    34.99,  '2024-02-03');
