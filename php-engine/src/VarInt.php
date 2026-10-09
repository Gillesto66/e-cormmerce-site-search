<?php
// Réalisée par Gillesto66 & Kiro
declare(strict_types=1);
namespace TagSearch;

/** Encodage variable-length integer (style Protocol Buffers). */
final class VarInt
{
    public static function encode(int $value): string
    {
        if ($value < 0) {
            throw new \InvalidArgumentException("VarInt: valeur négative non supportée : {$value}");
        }
        $out = '';
        while ($value >= 0x80) {
            $out .= chr(($value & 0x7F) | 0x80);
            $value >>= 7;
        }
        return $out . chr($value);
    }

    /** @return array{0: int, 1: int} [valeur, nouvel offset] */
    public static function decode(string $data, int $offset = 0): array
    {
        $result = 0;
        $shift  = 0;
        $len    = strlen($data);
        while (true) {
            if ($offset >= $len) {
                throw new \UnexpectedValueException('VarInt: données tronquées (offset hors limites).');
            }
            $byte = ord($data[$offset++]);
            $result |= ($byte & 0x7F) << $shift;
            if (($byte & 0x80) === 0) {
                break;
            }
            $shift += 7;
        }
        return [$result, $offset];
    }
}
