-- ============================================================================
-- NStone demo seed (local / CI). Safe sample data only — no real customers.
-- ============================================================================

INSERT INTO online_stock (name, type, color, origin, finish, thickness, dimensions, stock, price) VALUES
('Bianco Carrara CD', 'Carrara', 'White', 'Italy', 'Polished', 2.0, '305x152', 550.0, 75.0),
('Calacatta Gold', 'Marble', 'White/Gold', 'Italy', 'Polished', 3.0, '280x180', 85.0, 550.0),
('Travertine Beige', 'Travertine', 'Beige', 'Turkey', 'Honed', 2.5, '250x150', 200.0, 70.0),
('Granite Black', 'Granite', 'Black', 'Brazil', 'Polished', 2.0, '320x200', 120.0, 30.0),
('Quartz White', 'Quartz', 'White', 'Spain', 'Polished', 2.0, '300x200', 95.0, 70.0),
('Bianco Statuario', 'Marble', 'White', 'Italy', 'Polished', 2.0, '300x200', 180.0, 600.0),
('Nero Marquina', 'Marble', 'Black', 'Spain', 'Polished', 2.0, '280x180', 140.0, 50.0),
('Bardiglio Grey', 'Marble', 'Grey', 'Italy', 'Polished', 2.0, '305x152', 220.0, 40.0),
('Rosso Verona', 'Marble', 'Red', 'Italy', 'Polished', 3.0, '280x180', 75.0, 30.0),
('Botticino Classic', 'Limestone', 'Beige', 'Italy', 'Polished', 2.0, '300x200', 160.0, 50.0);

INSERT INTO quotations (cliente, materiale, numero_blocco, misure_cm, quantita_mq, prezzo_mq, status, valid_until) VALUES
('Luxury Interiors Ltd', 'Calacatta Borghini', 'B-2847', '310 x 185', 74.50, 450.0, 98, '2025-12-31'),
('Stone Design Studio', 'Bianco Carrara CD', 'B-1102', '295 x 160', 142.10, 185.0, 95, '2025-06-30'),
('Marble Masters Co.', 'Statuario Venato', 'B-9921', '280 x 150', 38.25, 720.0, 99, '2025-09-15'),
('Hotel Plaza Project', 'Travertino Romano', 'B-4432', '320 x 190', 210.00, 95.0, 92, '2026-01-01'),
('ArchiBuild Paris', 'Nero Marquina', 'B-0087', '305 x 175', 56.80, 210.0, 96, '2025-12-20'),
('Global Stone Inc', 'Grigio Carnico', 'B-5521', '290 x 165', 89.40, 145.0, 94, '2025-08-10');

INSERT INTO orders (order_id, client, product, machine, status, scheduled) VALUES
('ORD-2025-882', 'Cliente Test 01', 'Top Cucina Calacatta Gold', 'Linea Taglio 01', 'In Lavorazione', 'Oggi, 14:30');

INSERT INTO collection (transporter, transport_id, status, progress, driver, eta, destination) VALUES
('Trasportatore Test', '#12849', 'In transito', 65, 'Trucker Test', '16:30', 'Volargne');

INSERT INTO production (machine, status, current_work, completion, efficiency, consumption) VALUES
('Linea Taglio 01', 'Attivo', 'Blocco Calacatta #2847', 68, 93.9, 45.2);

INSERT INTO administration (invoice_number, client, amount_eur, date, status) VALUES
('INV-2024-001', 'Cliente Test', 15750.0, '2025-12-20', 'Pending'),
('INV-2025-002', 'Demo Client', 1000.0, '2025-12-22', 'Pending');
