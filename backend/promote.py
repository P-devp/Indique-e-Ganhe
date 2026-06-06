import sqlite3, sys
email = sys.argv[1] if len(sys.argv) > 1 else 'admin@retro.com'
conn = sqlite3.connect('retro.db')
conn.execute('UPDATE users SET role = ? WHERE email = ?', ('admin', email))
conn.commit()
r = conn.execute('SELECT email, role FROM users WHERE email = ?', (email,)).fetchone()
conn.close()
if r:
    print(f'{r[0]} promovido para {r[1]}')
else:
    print(f'Email {email} não encontrado')
