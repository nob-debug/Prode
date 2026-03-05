import sqlite3
import os

def patch_database():
    db_path = "sql_app.db"
    if not os.path.exists(db_path):
        print(f"Error: No se encontró la base de datos en {db_path}")
        return

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Verificar si la columna ya existe
        cursor.execute("PRAGMA table_info(usuarios)")
        columns = [row[1] for row in cursor.fetchall()]

        if "puntos_totales" not in columns:
            print("Agregando columna 'puntos_totales' a la tabla 'usuarios'...")
            cursor.execute("ALTER TABLE usuarios ADD COLUMN puntos_totales INTEGER DEFAULT 0")
            conn.commit()
            print("Columna agregada exitosamente.")
        else:
            print("La columna 'puntos_totales' ya existe.")

        conn.close()
    except Exception as e:
        print(f"Error al parchear la base de datos: {e}")

if __name__ == "__main__":
    patch_database()
