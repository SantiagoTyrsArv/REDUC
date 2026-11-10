-- Vector tile functions served by Martin (docs/04-api.md §2, "Teselas").
-- Both expose only the published map version of each active region.

CREATE OR REPLACE FUNCTION tiles_edge_accessibility(z integer, x integer, y integer)
RETURNS bytea AS $$
    SELECT COALESCE(ST_AsMVT(tile, 'edge_accessibility', 4096, 'geom'), ''::bytea)
    FROM (
        SELECT e.id,
               a.status,
               round(a.max_slope_pct::numeric, 1)::double precision AS slope_pct,
               a.surface_class::integer AS surface_class,
               a.verified,
               e.kind,
               ST_AsMVTGeom(ST_Transform(e.geom, 3857), ST_TileEnvelope(z, x, y), 4096, 64, true) AS geom
        FROM edge e
        JOIN edge_accessibility a ON a.edge_id = e.id
        JOIN region r ON r.published_version_id = e.map_version_id AND r.is_active
        WHERE e.geom && ST_Transform(ST_TileEnvelope(z, x, y), 4326)
    ) AS tile
    WHERE tile.geom IS NOT NULL;
$$ LANGUAGE sql STABLE PARALLEL SAFE;

CREATE OR REPLACE FUNCTION tiles_barrier(z integer, x integer, y integer)
RETURNS bytea AS $$
    SELECT COALESCE(ST_AsMVT(tile, 'barrier', 4096, 'geom'), ''::bytea)
    FROM (
        SELECT b.id::text AS id,
               b.class,
               b.severity,
               b.verification_status,
               ST_AsMVTGeom(ST_Transform(b.geom, 3857), ST_TileEnvelope(z, x, y), 4096, 64, true) AS geom
        FROM barrier b
        JOIN region r ON r.published_version_id = b.map_version_id AND r.is_active
        WHERE b.verification_status <> 'rejected'
          AND b.class NOT IN ('curb_ramp', 'ramp')
          AND b.geom && ST_Transform(ST_TileEnvelope(z, x, y), 4326)
    ) AS tile
    WHERE tile.geom IS NOT NULL;
$$ LANGUAGE sql STABLE PARALLEL SAFE;
