-- tests/schema.sql
--
-- Esquema REAL de easyfarma_dev en Aiven (MySQL 8.0.45), volcado con
-- SHOW CREATE TABLE el 2026-10-13. Solo DDL: ni una fila de datos.
--
-- POR QUE EXISTE ESTE FICHERO, y no un Base.metadata.create_all():
-- los modelos de app/models NO declaran ni una sola ForeignKey (consecuencia
-- de ddl-auto=none: el esquema de Aiven se hizo a mano). Un create_all()
-- construiria por tanto un esquema SIN las tres cascadas de abajo, y los dos
-- peores bugs del proyecto (pasos 6 y 9) pasarian en verde. Ver ESTRUCTURA §9.
--
-- DOS AJUSTES respecto a la salida literal de SHOW CREATE TABLE, los dos
-- a proposito:
--
--  1. BACKTICKS en vez de comillas dobles. Aiven lleva ANSI_QUOTES en el
--     sql_mode, asi que su SHOW CREATE TABLE emite "users". Cargado en un
--     MySQL con el sql_mode por defecto (el del contenedor), esas comillas
--     se leen como CADENA y el DDL revienta. Los backticks valen en los dos.
--
--  2. Las opciones de tabla (ENGINE / CHARSET / COLLATE) van escritas a mano,
--     con la TABLE_COLLATION leida de information_schema.TABLES en Aiven:
--     cuatro tablas en utf8mb4_general_ci y DOS en utf8mb4_0900_ai_ci
--     (activity_log y ventas_canceladas). Importa: sus columnas de texto no
--     declaran collation propia, asi que la heredan de la tabla.
--     InnoDB es obligado -- sin el no hay claves ajenas.
--     Se omite el AUTO_INCREMENT=n, que es estado de produccion y no esquema.
--
-- VERSION: Aiven corre 8.0.45 y pasa a 8.4 despues del 31/10/2026. Este
-- fichero se carga en las dos (ver tests/integration/conftest.py).

CREATE TABLE `users` (
  `id` int NOT NULL AUTO_INCREMENT,
  `username` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `password` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `enabled` tinyint(1) NOT NULL DEFAULT '1',
  `permiso` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT 'SELLER',
  PRIMARY KEY (`id`),
  UNIQUE KEY `username` (`username`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

CREATE TABLE `authorities` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `username` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `role` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  PRIMARY KEY (`id`),
  KEY `fk_users_authorities` (`username`),
  CONSTRAINT `fk_users_authorities` FOREIGN KEY (`username`) REFERENCES `users` (`username`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

CREATE TABLE `articulos` (
  `id` int NOT NULL AUTO_INCREMENT,
  `nombre` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `categoria` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `precio` double NOT NULL,
  `cantidad` int NOT NULL DEFAULT '0',
  `codigo` char(13) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `aemps_code` varchar(10) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `laboratorio` varchar(100) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `version` int NOT NULL DEFAULT '0',
  PRIMARY KEY (`id`),
  UNIQUE KEY `codigo_unico` (`codigo`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

CREATE TABLE `ventas` (
  `id` int NOT NULL AUTO_INCREMENT,
  `fecha` date NOT NULL,
  `hora` time NOT NULL,
  `id_username` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `dnicliente` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL,
  `nameproducto` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL,
  `cantidad` int NOT NULL,
  `importe` double NOT NULL,
  `codigo` char(13) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  PRIMARY KEY (`id`),
  KEY `fk_usuario_ventas` (`id_username`),
  KEY `fk_articulos_ventas` (`codigo`),
  CONSTRAINT `fk_articulos_ventas` FOREIGN KEY (`codigo`) REFERENCES `articulos` (`codigo`) ON DELETE CASCADE,
  CONSTRAINT `fk_usuario_ventas` FOREIGN KEY (`id_username`) REFERENCES `users` (`username`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

CREATE TABLE `ventas_canceladas` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `nombre_producto` varchar(255) NOT NULL,
  `cantidad` int NOT NULL,
  `importe` decimal(10,2) NOT NULL,
  `responsable` varchar(50) NOT NULL,
  `fecha` datetime DEFAULT CURRENT_TIMESTAMP,
  `status` enum('CANCELLED','RETURNED') NOT NULL DEFAULT 'CANCELLED',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `activity_log` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `username` varchar(50) NOT NULL,
  `action` varchar(50) NOT NULL,
  `detail` varchar(255) DEFAULT NULL,
  `ip_address` varchar(45) DEFAULT NULL,
  `fecha` date NOT NULL,
  `hora` time NOT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
