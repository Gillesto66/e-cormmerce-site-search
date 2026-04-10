<?php
// Réalisée par Gillesto66 & Kiro
declare(strict_types=1);
namespace TagSearch;

// Constantes de scoring — synchronisées avec shared-assets/catalog.json
const BM25_K1            = 1.5;
const BM25_B             = 0.75;
const BM25_CAP           = 10.0;
const BM25_FLOOR         = 0.05;
const QUALITY_EXPONENT   = 1.5;
const PRIOR_MEAN         = 3.5;
const PRIOR_WEIGHT       = 10.0;
const TYPE_MISMATCH      = 0.1;
const NICHE_BOOST        = 1.2;
const PROXIMITY_BONUS    = 1.15;
const PRICE_BUDGET_BOOST = 1.1;
