"""Read-only classic-PCAP UDP/RTP-header summary; never print payloads."""
import collections
import datetime
import hashlib
import ipaddress
from pathlib import Path
import struct
import sys


def packets(path):
    data = Path(path).read_bytes()
    magic = data[:4]
    endian, nanos = {
        b'\xd4\xc3\xb2\xa1': ('<', False), b'\xa1\xb2\xc3\xd4': ('>', False),
        b'\x4d\x3c\xb2\xa1': ('<', True), b'\xa1\xb2\x3c\x4d': ('>', True),
    }[magic]
    link = struct.unpack_from(endian + 'I', data, 20)[0]
    offset = 24
    while offset < len(data):
        sec, frac, size, original = struct.unpack_from(endian + 'IIII', data, offset)
        offset += 16
        frame = data[offset:offset + size]
        offset += size
        if len(frame) != size:
            raise ValueError('truncated PCAP record')
        cooked_type = struct.unpack_from('>H', frame)[0] if link == 113 else None
        ip = frame[16:] if link == 113 else frame if link in (101, 12) else None
        if not ip:
            raise ValueError(f'unsupported link type {link}')
        version = ip[0] >> 4
        if version == 4:
            proto, pos = ip[9], (ip[0] & 15) * 4
            src, dst = map(str, (ipaddress.ip_address(ip[12:16]), ipaddress.ip_address(ip[16:20])))
        elif version == 6:
            proto, pos = ip[6], 40
            src, dst = map(str, (ipaddress.ip_address(ip[8:24]), ipaddress.ip_address(ip[24:40])))
            # Extension headers visible within the bounded snaplen.
            while proto in (0, 43, 60) and pos + 2 <= len(ip):
                proto, length = ip[pos], (ip[pos + 1] + 1) * 8
                pos += length
        else:
            continue
        if proto != 17 or len(ip) < pos + 8:
            continue
        sport, dport, udp_len = struct.unpack_from('>HHH', ip, pos)
        payload = ip[pos + 8:]
        rtp = None
        # RTCP SR/RR share version 2 but do not carry RTP sequence/timestamp.
        if len(payload) >= 12 and payload[0] >> 6 == 2 and not 192 <= payload[1] <= 223:
            rtp = (payload[1] & 127, *struct.unpack_from('>HII', payload, 2))
        yield dict(time=sec + frac / (1e9 if nanos else 1e6), flow=(src, sport, dst, dport),
                   udp_len=udp_len, rtp=rtp, cooked_type=cooked_type,
                   fingerprint=hashlib.sha256(ip[:min(len(ip), 80)]).hexdigest())


def main(paths):
    captures = []
    for path in paths:
        rows = list(packets(path))
        captures.append(rows)
        print(Path(path).name, 'UDP packets=', len(rows))
        grouped = collections.defaultdict(list)
        for row in rows:
            grouped[row['flow']].append(row)
        for flow, group in grouped.items():
            rtp = [r['rtp'] for r in group if r['rtp']]
            times = [r['time'] for r in group]
            stamp = lambda t: datetime.datetime.fromtimestamp(t, datetime.timezone(datetime.timedelta(hours=8))).isoformat()
            print(' flow=', flow, 'count=', len(group), 'window=', (stamp(min(times)), stamp(max(times))),
                  'udp_lengths=', dict(collections.Counter(r['udp_len'] for r in group)),
                  'cooked_types=', dict(collections.Counter(r['cooked_type'] for r in group)))
            if rtp:
                print(' RTP_header_candidates=', len(rtp), 'PT=', dict(collections.Counter(r[0] for r in rtp)),
                      'first_last=', (rtp[0], rtp[-1]),
                      'seq_step=', dict(collections.Counter((b[1] - a[1]) % 65536 for a, b in zip(rtp, rtp[1:]))),
                      'timestamp_step=', dict(collections.Counter((b[2] - a[2]) % 2**32 for a, b in zip(rtp, rtp[1:]))))
    if len(captures) == 2:
        a, b = [collections.Counter(r['fingerprint'] for r in rows) for rows in captures]
        print('Matching captured IP prefixes=', sum((a & b).values()), 'only_first=', sum((a - b).values()),
              'only_second=', sum((b - a).values()))


if __name__ == '__main__':
    main(sys.argv[1:])
