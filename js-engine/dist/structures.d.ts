/**
 * tagsearch/structures.ts
 * Réalisée par Gillesto66 & Kiro
 * DAWG + LRUCache — portage de structures.py
 * Note : pas de __slots__ en TS, mais les classes sont naturellement compactes.
 */
declare class DAWGNode {
    children: Map<string, DAWGNode>;
    isTerminal: boolean;
    tag: string | null;
    frozen: boolean;
}
export declare class DAWG {
    readonly root: DAWGNode;
    private minimized;
    private lastWord;
    private unchecked;
    private structuralKey;
    private nodeId;
    private minimize;
    insert(word: string): void;
    finish(): void;
    static build(tags: string[]): DAWG;
    contains(word: string): boolean;
    autocomplete(prefix: string): string[];
    private _dfs;
    fuzzySearch(query: string, maxDistance?: number): string[];
    private _fuzzyDfs;
}
export declare class LRUCache<V> {
    private readonly capacity;
    private cache;
    constructor(capacity: number);
    get(key: string): V | undefined;
    put(key: string, value: V): void;
    invalidate(): void;
}
export {};
//# sourceMappingURL=structures.d.ts.map