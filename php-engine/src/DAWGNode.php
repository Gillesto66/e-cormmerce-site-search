<?php
// Réalisée par Gillesto66 & Kiro
declare(strict_types=1);
namespace TagSearch;

/**
 * Nœud DAWG. Le mot n'est PAS stocké dans le nœud (reconstruit par le chemin) : c'est ce
 * qui permet le partage de suffixes. `id` sert uniquement à la clé structurelle.
 */
final class DAWGNode
{
    /** @var array<string|int, DAWGNode> clé = un point de code (attention : "4" devient la clé entière 4) */
    public array $children = [];
    public bool $isTerminal = false;

    public function __construct(public readonly int $id) {}
}
