import sqlite3

conn = sqlite3.connect('data/nstonellm.db')
cursor = conn.cursor()

# Verifica tabelle
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = cursor.fetchall()
print('Tabelle trovate:')
for t in tables:
    print(f'  - {t[0]}')

print('\nRecord per tabella:')
cursor.execute("""
    SELECT 'online_stock', COUNT(*) FROM online_stock 
    UNION ALL SELECT 'quotations', COUNT(*) FROM quotations 
    UNION ALL SELECT 'orders', COUNT(*) FROM orders 
    UNION ALL SELECT 'collection', COUNT(*) FROM collection 
    UNION ALL SELECT 'production', COUNT(*) FROM production 
    UNION ALL SELECT 'administration', COUNT(*) FROM administration
""")
results = cursor.fetchall()
for r in results:
    print(f'  {r[0]}: {r[1]} record')

conn.close()





