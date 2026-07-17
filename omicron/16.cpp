#include <algorithm>
#include <cctype>
#include <cerrno>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <map>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

using std::map;
using std::string;
using std::vector;

static void fail(const string &msg) {
    throw std::runtime_error(msg);
}

static string trim(const string &s) {
    size_t a = 0;
    while (a < s.size() && std::isspace(static_cast<unsigned char>(s[a]))) ++a;
    size_t b = s.size();
    while (b > a && std::isspace(static_cast<unsigned char>(s[b - 1]))) --b;
    return s.substr(a, b - a);
}

class BigUInt {
public:
    static const uint32_t BASE = 1000000000U;
    vector<uint32_t> d; // little-endian base-1e9 limbs.

    BigUInt() {}
    explicit BigUInt(uint64_t v) {
        while (v) {
            d.push_back(static_cast<uint32_t>(v % BASE));
            v /= BASE;
        }
    }

    bool isZero() const { return d.empty(); }

    static BigUInt fromDecimal(const string &text, const string &field) {
        if (text.empty()) fail("malformed decimal integer for " + field + ": empty");
        BigUInt v(0);
        for (size_t i = 0; i < text.size(); ++i) {
            unsigned char ch = static_cast<unsigned char>(text[i]);
            if (!std::isdigit(ch)) fail("malformed decimal integer for " + field + ": " + text);
            v = v.mulSmall(10);
            v.addSmall(static_cast<uint32_t>(ch - '0'));
        }
        return v;
    }

    string str() const {
        if (d.empty()) return "0";
        std::ostringstream out;
        out << d.back();
        for (size_t i = d.size() - 1; i-- > 0;) {
            out << std::setw(9) << std::setfill('0') << d[i];
        }
        return out.str();
    }

    void normalize() {
        while (!d.empty() && d.back() == 0) d.pop_back();
    }

    int cmp(const BigUInt &o) const {
        if (d.size() != o.d.size()) return d.size() < o.d.size() ? -1 : 1;
        for (size_t i = d.size(); i-- > 0;) {
            if (d[i] != o.d[i]) return d[i] < o.d[i] ? -1 : 1;
        }
        return 0;
    }

    bool operator<(const BigUInt &o) const { return cmp(o) < 0; }
    bool operator>(const BigUInt &o) const { return cmp(o) > 0; }
    bool operator<=(const BigUInt &o) const { return cmp(o) <= 0; }
    bool operator>=(const BigUInt &o) const { return cmp(o) >= 0; }
    bool operator==(const BigUInt &o) const { return cmp(o) == 0; }
    bool operator!=(const BigUInt &o) const { return cmp(o) != 0; }

    void addSmall(uint32_t v) {
        uint64_t carry = v;
        size_t i = 0;
        while (carry) {
            if (i == d.size()) d.push_back(0);
            uint64_t cur = static_cast<uint64_t>(d[i]) + carry;
            d[i] = static_cast<uint32_t>(cur % BASE);
            carry = cur / BASE;
            ++i;
        }
    }

    BigUInt add(const BigUInt &o) const {
        BigUInt r;
        const size_t n = std::max(d.size(), o.d.size());
        r.d.assign(n, 0);
        uint64_t carry = 0;
        for (size_t i = 0; i < n; ++i) {
            uint64_t cur = carry;
            if (i < d.size()) cur += d[i];
            if (i < o.d.size()) cur += o.d[i];
            r.d[i] = static_cast<uint32_t>(cur % BASE);
            carry = cur / BASE;
        }
        if (carry) r.d.push_back(static_cast<uint32_t>(carry));
        return r;
    }

    BigUInt sub(const BigUInt &o) const {
        if (*this < o) fail("internal BigUInt subtraction precondition failed");
        BigUInt r;
        r.d.assign(d.size(), 0);
        int64_t borrow = 0;
        for (size_t i = 0; i < d.size(); ++i) {
            int64_t cur = static_cast<int64_t>(d[i]) - borrow - (i < o.d.size() ? o.d[i] : 0);
            if (cur < 0) {
                cur += BASE;
                borrow = 1;
            } else {
                borrow = 0;
            }
            r.d[i] = static_cast<uint32_t>(cur);
        }
        r.normalize();
        return r;
    }

    BigUInt mulSmall(uint64_t m) const {
        if (isZero() || m == 0) return BigUInt(0);
        BigUInt r;
        r.d.assign(d.size(), 0);
        uint64_t carry = 0;
        for (size_t i = 0; i < d.size(); ++i) {
            uint64_t cur = static_cast<uint64_t>(d[i]) * m + carry;
            r.d[i] = static_cast<uint32_t>(cur % BASE);
            carry = cur / BASE;
        }
        while (carry) {
            r.d.push_back(static_cast<uint32_t>(carry % BASE));
            carry /= BASE;
        }
        return r;
    }

    BigUInt mul(const BigUInt &o) const {
        if (isZero() || o.isZero()) return BigUInt(0);
        BigUInt r;
        r.d.assign(d.size() + o.d.size() + 1, 0);
        for (size_t i = 0; i < d.size(); ++i) {
            uint64_t carry = 0;
            for (size_t j = 0; j < o.d.size() || carry; ++j) {
                if (i + j >= r.d.size()) r.d.push_back(0);
                uint64_t cur = r.d[i + j] + carry;
                if (j < o.d.size()) cur += static_cast<uint64_t>(d[i]) * o.d[j];
                r.d[i + j] = static_cast<uint32_t>(cur % BASE);
                carry = cur / BASE;
            }
        }
        r.normalize();
        return r;
    }

    BigUInt divSmall(uint32_t m, uint32_t *remOut = nullptr) const {
        if (m == 0) fail("division by zero");
        BigUInt q;
        q.d.assign(d.size(), 0);
        uint64_t rem = 0;
        for (size_t i = d.size(); i-- > 0;) {
            uint64_t cur = rem * BASE + d[i];
            q.d[i] = static_cast<uint32_t>(cur / m);
            rem = cur % m;
        }
        q.normalize();
        if (remOut) *remOut = static_cast<uint32_t>(rem);
        return q;
    }

    bool isOdd() const {
        return !d.empty() && (d[0] & 1U);
    }

    static std::pair<BigUInt, BigUInt> divmod(const BigUInt &a, const BigUInt &b) {
        if (b.isZero()) fail("division by zero");
        if (a < b) return std::make_pair(BigUInt(0), a);
        if (b.d.size() == 1) {
            uint32_t rem = 0;
            BigUInt q = a.divSmall(b.d[0], &rem);
            return std::make_pair(q, BigUInt(rem));
        }

        // Decimal long division keeps this implementation small and fully exact.
        string dec = a.str();
        string qdigits;
        BigUInt rem(0);
        bool seen = false;
        for (size_t i = 0; i < dec.size(); ++i) {
            rem = rem.mulSmall(10);
            rem.addSmall(static_cast<uint32_t>(dec[i] - '0'));
            int lo = 0, hi = 9, best = 0;
            while (lo <= hi) {
                int mid = (lo + hi) / 2;
                BigUInt prod = b.mulSmall(static_cast<uint32_t>(mid));
                if (prod <= rem) {
                    best = mid;
                    lo = mid + 1;
                } else {
                    hi = mid - 1;
                }
            }
            BigUInt prod = b.mulSmall(static_cast<uint32_t>(best));
            rem = rem.sub(prod);
            if (best != 0 || seen) {
                qdigits.push_back(static_cast<char>('0' + best));
                seen = true;
            }
        }
        if (!seen) qdigits = "0";
        return std::make_pair(BigUInt::fromDecimal(qdigits, "internal quotient"), rem);
    }

    BigUInt div(const BigUInt &b) const { return divmod(*this, b).first; }
    BigUInt mod(const BigUInt &b) const { return divmod(*this, b).second; }
};

static BigUInt operator+(const BigUInt &a, const BigUInt &b) { return a.add(b); }
static BigUInt operator-(const BigUInt &a, const BigUInt &b) { return a.sub(b); }
static BigUInt operator*(const BigUInt &a, const BigUInt &b) { return a.mul(b); }

static BigUInt powUInt(BigUInt base, size_t exp) {
    BigUInt result(1);
    while (exp) {
        if (exp & 1U) result = result * base;
        exp >>= 1U;
        if (exp) base = base * base;
    }
    return result;
}

static BigUInt gcdUInt(BigUInt a, BigUInt b) {
    while (!b.isZero()) {
        BigUInt r = a.mod(b);
        a = b;
        b = r;
    }
    return a;
}

static BigUInt kthRootCeil(const BigUInt &n, int k) {
    if (k < 1 || k > 6) fail("internal kth-root exponent outside 1..6");
    if (n.isZero()) return BigUInt(0);
    if (k == 1) return n;
    BigUInt one(1);
    BigUInt lo(0), hi(1);
    while (powUInt(hi, static_cast<size_t>(k)) < n) hi = hi.mulSmall(2);
    while ((lo + one) < hi) {
        BigUInt mid = (lo + hi).divSmall(2);
        if (powUInt(mid, static_cast<size_t>(k)) >= n) hi = mid;
        else lo = mid;
    }
    return hi;
}

class BigInt {
public:
    int sign; // -1, 0, +1
    BigUInt mag;

    BigInt() : sign(0), mag(0) {}
    explicit BigInt(int v) : sign(0), mag(0) {
        if (v < 0) {
            sign = -1;
            mag = BigUInt(static_cast<uint64_t>(-static_cast<int64_t>(v)));
        } else if (v > 0) {
            sign = 1;
            mag = BigUInt(static_cast<uint64_t>(v));
        }
    }
    BigInt(int s, const BigUInt &m) : sign(s), mag(m) { normalize(); }

    void normalize() {
        if (mag.isZero()) sign = 0;
        else if (sign < 0) sign = -1;
        else sign = 1;
    }

    string str() const {
        if (sign == 0) return "0";
        return sign < 0 ? "-" + mag.str() : mag.str();
    }

    static BigInt zigzag(const BigUInt &n) {
        if (n.isZero()) return BigInt();
        if (n.isOdd()) {
            BigUInt t = (n + BigUInt(1)).divSmall(2);
            return BigInt(1, t);
        }
        BigUInt t = n.divSmall(2);
        return BigInt(-1, t);
    }

    BigInt divExactPositive(const BigUInt &g) const {
        if (g.isZero()) fail("internal BigInt division by zero");
        if (sign == 0) return BigInt();
        std::pair<BigUInt, BigUInt> qr = BigUInt::divmod(mag, g);
        if (!qr.second.isZero()) fail("internal non-exact BigInt division");
        return BigInt(sign, qr.first);
    }
};

static string jsonEscape(const string &s) {
    std::ostringstream out;
    out << '"';
    for (size_t i = 0; i < s.size(); ++i) {
        unsigned char c = static_cast<unsigned char>(s[i]);
        switch (c) {
            case '"': out << "\\\""; break;
            case '\\': out << "\\\\"; break;
            case '\b': out << "\\b"; break;
            case '\f': out << "\\f"; break;
            case '\n': out << "\\n"; break;
            case '\r': out << "\\r"; break;
            case '\t': out << "\\t"; break;
            default:
                if (c < 0x20) {
                    out << "\\u" << std::hex << std::setw(4) << std::setfill('0') << static_cast<int>(c)
                        << std::dec << std::setfill(' ');
                } else {
                    out << static_cast<char>(c);
                }
        }
    }
    out << '"';
    return out.str();
}

static string escapeByte(unsigned char c) {
    switch (c) {
        case '\n': return "\\n";
        case '\r': return "\\r";
        case '\t': return "\\t";
        case ' ': return "\\s";
        case '\\': return "\\\\";
        case '"': return "\\\"";
        default:
            if (c < 0x20 || c >= 0x7f) {
                std::ostringstream out;
                out << "\\x" << std::hex << std::setw(2) << std::setfill('0') << static_cast<int>(c);
                return out.str();
            }
            return string(1, static_cast<char>(c));
    }
}

static string safePreview(const string &s, size_t limit = 80) {
    string out;
    size_t used = 0;
    for (size_t i = 0; i < s.size() && used < limit; ++i, ++used) out += escapeByte(static_cast<unsigned char>(s[i]));
    if (s.size() > limit) out += "...";
    return out;
}

static void utf8Append(string &out, uint32_t cp) {
    if (cp <= 0x7f) {
        out.push_back(static_cast<char>(cp));
    } else if (cp <= 0x7ff) {
        out.push_back(static_cast<char>(0xc0 | (cp >> 6)));
        out.push_back(static_cast<char>(0x80 | (cp & 0x3f)));
    } else if (cp <= 0xffff) {
        out.push_back(static_cast<char>(0xe0 | (cp >> 12)));
        out.push_back(static_cast<char>(0x80 | ((cp >> 6) & 0x3f)));
        out.push_back(static_cast<char>(0x80 | (cp & 0x3f)));
    } else if (cp <= 0x10ffff) {
        out.push_back(static_cast<char>(0xf0 | (cp >> 18)));
        out.push_back(static_cast<char>(0x80 | ((cp >> 12) & 0x3f)));
        out.push_back(static_cast<char>(0x80 | ((cp >> 6) & 0x3f)));
        out.push_back(static_cast<char>(0x80 | (cp & 0x3f)));
    } else {
        fail("invalid unicode code point in JSON string");
    }
}

struct Json {
    enum Type { NUL, BOOL, NUMBER, STRING, ARRAY, OBJECT } type;
    bool b;
    string s;
    vector<Json> a;
    map<string, Json> o;
    Json() : type(NUL), b(false) {}
};

class JsonParser {
public:
    explicit JsonParser(const string &text) : src(text), pos(0) {}
    Json parse() {
        Json v = parseValue();
        skipWs();
        if (pos != src.size()) fail("malformed JSON: trailing characters at byte " + std::to_string(pos));
        return v;
    }

private:
    string src;
    size_t pos;

    void skipWs() {
        while (pos < src.size() && std::isspace(static_cast<unsigned char>(src[pos]))) ++pos;
    }
    char peek() {
        skipWs();
        if (pos >= src.size()) fail("malformed JSON: unexpected end of input");
        return src[pos];
    }
    char get() {
        if (pos >= src.size()) fail("malformed JSON: unexpected end of input");
        return src[pos++];
    }
    static int hexVal(char c) {
        if (c >= '0' && c <= '9') return c - '0';
        if (c >= 'a' && c <= 'f') return 10 + c - 'a';
        if (c >= 'A' && c <= 'F') return 10 + c - 'A';
        return -1;
    }
    uint32_t readU4() {
        if (pos + 4 > src.size()) fail("malformed JSON string: incomplete unicode escape");
        uint32_t v = 0;
        for (int i = 0; i < 4; ++i) {
            int h = hexVal(src[pos++]);
            if (h < 0) fail("malformed JSON string: invalid unicode escape");
            v = (v << 4) | static_cast<uint32_t>(h);
        }
        return v;
    }
    Json parseValue() {
        skipWs();
        if (pos >= src.size()) fail("malformed JSON: expected value");
        char c = src[pos];
        if (c == '"') return parseString();
        if (c == '{') return parseObject();
        if (c == '[') return parseArray();
        if (c == '-' || std::isdigit(static_cast<unsigned char>(c))) return parseNumber();
        if (src.compare(pos, 4, "true") == 0) {
            pos += 4;
            Json v;
            v.type = Json::BOOL;
            v.b = true;
            return v;
        }
        if (src.compare(pos, 5, "false") == 0) {
            pos += 5;
            Json v;
            v.type = Json::BOOL;
            v.b = false;
            return v;
        }
        if (src.compare(pos, 4, "null") == 0) {
            pos += 4;
            return Json();
        }
        fail("malformed JSON: expected value at byte " + std::to_string(pos));
        return Json();
    }
    Json parseString() {
        Json v;
        v.type = Json::STRING;
        if (get() != '"') fail("internal parser error");
        while (pos < src.size()) {
            char c = get();
            if (c == '"') return v;
            if (static_cast<unsigned char>(c) < 0x20) fail("malformed JSON string: unescaped control character");
            if (c != '\\') {
                v.s.push_back(c);
                continue;
            }
            char e = get();
            switch (e) {
                case '"': v.s.push_back('"'); break;
                case '\\': v.s.push_back('\\'); break;
                case '/': v.s.push_back('/'); break;
                case 'b': v.s.push_back('\b'); break;
                case 'f': v.s.push_back('\f'); break;
                case 'n': v.s.push_back('\n'); break;
                case 'r': v.s.push_back('\r'); break;
                case 't': v.s.push_back('\t'); break;
                case 'u': {
                    uint32_t cp = readU4();
                    if (cp >= 0xd800 && cp <= 0xdbff) {
                        if (pos + 2 > src.size() || src[pos] != '\\' || src[pos + 1] != 'u') {
                            fail("malformed JSON string: high surrogate without low surrogate");
                        }
                        pos += 2;
                        uint32_t lo = readU4();
                        if (lo < 0xdc00 || lo > 0xdfff) fail("malformed JSON string: invalid low surrogate");
                        cp = 0x10000 + ((cp - 0xd800) << 10) + (lo - 0xdc00);
                    } else if (cp >= 0xdc00 && cp <= 0xdfff) {
                        fail("malformed JSON string: low surrogate without high surrogate");
                    }
                    utf8Append(v.s, cp);
                    break;
                }
                default:
                    fail("malformed JSON string: invalid escape");
            }
        }
        fail("malformed JSON string: missing closing quote");
        return v;
    }
    Json parseNumber() {
        Json v;
        v.type = Json::NUMBER;
        size_t start = pos;
        if (src[pos] == '-') ++pos;
        if (pos >= src.size()) fail("malformed JSON number");
        if (src[pos] == '0') {
            ++pos;
        } else if (src[pos] >= '1' && src[pos] <= '9') {
            while (pos < src.size() && std::isdigit(static_cast<unsigned char>(src[pos]))) ++pos;
        } else {
            fail("malformed JSON number");
        }
        if (pos < src.size() && src[pos] == '.') {
            ++pos;
            if (pos >= src.size() || !std::isdigit(static_cast<unsigned char>(src[pos]))) fail("malformed JSON number");
            while (pos < src.size() && std::isdigit(static_cast<unsigned char>(src[pos]))) ++pos;
        }
        if (pos < src.size() && (src[pos] == 'e' || src[pos] == 'E')) {
            ++pos;
            if (pos < src.size() && (src[pos] == '+' || src[pos] == '-')) ++pos;
            if (pos >= src.size() || !std::isdigit(static_cast<unsigned char>(src[pos]))) fail("malformed JSON number");
            while (pos < src.size() && std::isdigit(static_cast<unsigned char>(src[pos]))) ++pos;
        }
        v.s = src.substr(start, pos - start);
        return v;
    }
    Json parseArray() {
        Json v;
        v.type = Json::ARRAY;
        get();
        skipWs();
        if (pos < src.size() && src[pos] == ']') {
            ++pos;
            return v;
        }
        while (true) {
            v.a.push_back(parseValue());
            skipWs();
            char c = get();
            if (c == ']') break;
            if (c != ',') fail("malformed JSON array: expected comma or closing bracket");
        }
        return v;
    }
    Json parseObject() {
        Json v;
        v.type = Json::OBJECT;
        get();
        skipWs();
        if (pos < src.size() && src[pos] == '}') {
            ++pos;
            return v;
        }
        while (true) {
            skipWs();
            if (pos >= src.size() || src[pos] != '"') fail("malformed JSON object: expected string key");
            Json key = parseString();
            skipWs();
            if (get() != ':') fail("malformed JSON object: expected colon after key");
            if (v.o.count(key.s)) fail("malformed JSON object: duplicate key '" + key.s + "'");
            v.o[key.s] = parseValue();
            skipWs();
            char c = get();
            if (c == '}') break;
            if (c != ',') fail("malformed JSON object: expected comma or closing brace");
        }
        return v;
    }
};

static const Json *findField(const Json &j, const string &name) {
    if (j.type != Json::OBJECT) return nullptr;
    map<string, Json>::const_iterator it = j.o.find(name);
    if (it == j.o.end()) return nullptr;
    return &it->second;
}

static const Json *needFieldPtr(const Json &j, string name, string where) {
    const Json *p = findField(j, name);
    if (!p) fail("missing config field " + where + "." + name);
    return p;
}

static string jsonStringField(const Json &j, const string &field, const string &where) {
    const Json &v = *needFieldPtr(j, field, where);
    if (v.type != Json::STRING) fail("config field " + where + "." + field + " must be a string");
    return v.s;
}

static string integerTextFromJson(const Json &v, const string &field) {
    if (v.type == Json::NUMBER || v.type == Json::STRING) return v.s;
    fail("config field " + field + " must be an integer number or decimal string");
    return "";
}

static size_t parseSizeTDecimal(const string &text, const string &field) {
    if (text.empty()) fail("malformed nonnegative integer for " + field);
    if (text[0] == '-') fail("negative integer rejected for " + field);
    size_t v = 0;
    for (size_t i = 0; i < text.size(); ++i) {
        if (!std::isdigit(static_cast<unsigned char>(text[i]))) fail("malformed nonnegative integer for " + field + ": " + text);
        size_t digit = static_cast<size_t>(text[i] - '0');
        if (v > (std::numeric_limits<size_t>::max() - digit) / 10) fail("integer too large for this implementation field " + field);
        v = v * 10 + digit;
    }
    return v;
}

static size_t jsonSizeTField(const Json &j, const string &field, const string &where) {
    const Json &v = *needFieldPtr(j, field, where);
    return parseSizeTDecimal(integerTextFromJson(v, where + "." + field), where + "." + field);
}

enum LengthMode { FIXED, VARIABLE };

struct ComponentSpec {
    string name;
    string alphabet;
    LengthMode mode;
    size_t fixed = 0;
    size_t minLen = 0;
    size_t maxLen = 0;
    BigUInt domain;
    BigUInt modulus;
    bool explicitModulus = false;
    vector<int> byteIndex;
};

struct ComponentValue {
    string input;
    size_t charLength = 0;
    size_t uniqueCount = 0;
    vector<string> uniqueSymbols;
    string preview;
    BigUInt rawId;
    BigUInt modulus;
    BigUInt residue;
    BigInt mappedSigned;
    BigUInt mappedPositive;
    string mappedValue;
    string canonical;
};

struct ScalarInfo {
    BigInt P;
    BigUInt Q;
    BigInt M;
    BigUInt G;
    BigInt Alpha;
    BigUInt Beta;
    BigInt AlphaReduced;
    BigUInt BetaReduced;
    string expression;
    string status;
};

struct InstanceResult {
    vector<ComponentValue> comp;
    ScalarInfo scalar;
    BigUInt rowOrdinal;
};

struct SeedSettings {
    int outputLength = 1;
    string seedFile = "19.txt";
    string basisOut = "20.txt";
    string mode = "strict";
    string basisPolicy = "ordered_with_repetition";
    bool emitGeneratedSeed = true;
};

struct OutputSettings {
    string format = "json";
    string path;
};

struct Config {
    string path;
    size_t instanceCount = 0;
    vector<ComponentSpec> components;
    vector<map<string, string> > instances;
    SeedSettings seed;
    OutputSettings output;
    bool inlineInstancesPresent = false;
};

static const char *COMPONENT_NAMES[6] = {"p", "q", "m", "g", "alpha", "beta"};

static bool isSignedSlot(size_t i) {
    return i == 0 || i == 2 || i == 4;
}

static BigUInt computeDomain(size_t r, LengthMode mode, size_t fixed, size_t minLen, size_t maxLen) {
    BigUInt br(static_cast<uint64_t>(r));
    if (mode == FIXED) return powUInt(br, fixed);
    BigUInt sum(0);
    for (size_t ell = minLen; ell <= maxLen; ++ell) {
        sum = sum + powUInt(br, ell);
        if (ell == std::numeric_limits<size_t>::max()) break;
    }
    return sum;
}

static void buildIndex(ComponentSpec &c) {
    if (c.alphabet.empty()) fail("component " + c.name + " alphabet must not be empty");
    if (c.alphabet.size() > static_cast<size_t>(std::numeric_limits<uint32_t>::max())) {
        fail("component " + c.name + " alphabet too large for small-radix operations");
    }
    c.byteIndex.assign(256, -1);
    for (size_t i = 0; i < c.alphabet.size(); ++i) {
        unsigned char b = static_cast<unsigned char>(c.alphabet[i]);
        if (c.byteIndex[b] >= 0) fail("component " + c.name + " alphabet contains duplicate decoded byte symbol " + escapeByte(b));
        c.byteIndex[b] = static_cast<int>(i);
    }
}

static ComponentSpec parseComponent(const Json &j, const string &name) {
    if (j.type != Json::OBJECT) fail("component " + name + " must be an object");
    ComponentSpec c;
    c.name = name;
    c.alphabet = jsonStringField(j, "alphabet", "components." + name);
    buildIndex(c);
    string compWhere = "components." + name;
    const Json &len = *needFieldPtr(j, "length", compWhere);
    if (len.type != Json::OBJECT) fail("components." + name + ".length must be an object");
    string lenWhere = compWhere + ".length";
    string mode = jsonStringField(len, "mode", lenWhere);
    if (mode == "fixed") {
        c.mode = FIXED;
        c.fixed = jsonSizeTField(len, "value", lenWhere);
    } else if (mode == "variable") {
        c.mode = VARIABLE;
        c.minLen = jsonSizeTField(len, "min", lenWhere);
        c.maxLen = jsonSizeTField(len, "max", lenWhere);
        if (c.minLen > c.maxLen) fail("components." + name + ".length min must be <= max");
    } else {
        fail("components." + name + ".length.mode must be fixed or variable");
    }
    c.domain = computeDomain(c.alphabet.size(), c.mode, c.fixed, c.minLen, c.maxLen);
    if (c.domain.isZero()) fail("component " + name + " raw domain size is zero");
    const Json *mod = findField(j, "modulus");
    if (mod) {
        string t = integerTextFromJson(*mod, "components." + name + ".modulus");
        if (!t.empty() && t[0] == '-') fail("components." + name + ".modulus must be positive");
        c.modulus = BigUInt::fromDecimal(t, "components." + name + ".modulus");
        if (c.modulus.isZero()) fail("components." + name + ".modulus must be positive");
        c.explicitModulus = true;
    } else {
        c.modulus = c.domain;
    }
    return c;
}

static Config parseConfigText(const string &text, const string &path) {
    Json root = JsonParser(text).parse();
    if (root.type != Json::OBJECT) fail("17.txt JSON root must be an object");
    Config cfg;
    cfg.path = path;
    const Json *cnt = findField(root, "instance_count");
    if (cnt) cfg.instanceCount = parseSizeTDecimal(integerTextFromJson(*cnt, "instance_count"), "instance_count");
    string rootWhere;
    const Json &components = *needFieldPtr(root, "components", rootWhere);
    if (components.type != Json::OBJECT) fail("config field components must be an object");
    for (int i = 0; i < 6; ++i) {
        string name = COMPONENT_NAMES[i];
        string componentsWhere = "components";
        const Json &cj = *needFieldPtr(components, name, componentsWhere);
        cfg.components.push_back(parseComponent(cj, name));
    }
    const Json *inst = findField(root, "instances");
    if (inst) {
        if (inst->type != Json::ARRAY) fail("config field instances must be an array");
        cfg.inlineInstancesPresent = true;
        for (size_t i = 0; i < inst->a.size(); ++i) {
            if (inst->a[i].type != Json::OBJECT) fail("instances[" + std::to_string(i) + "] must be an object");
            map<string, string> one;
            for (int c = 0; c < 6; ++c) {
                string name = COMPONENT_NAMES[c];
                one[name] = jsonStringField(inst->a[i], name, "instances[" + std::to_string(i) + "]");
            }
            cfg.instances.push_back(one);
        }
        if (cnt && cfg.instanceCount != cfg.instances.size()) {
            fail("instance_count mismatch: instance_count=" + std::to_string(cfg.instanceCount) +
                 " but inline instances has " + std::to_string(cfg.instances.size()));
        }
        if (!cnt) cfg.instanceCount = cfg.instances.size();
    }
    const Json *seed = findField(root, "seed");
    if (seed) {
        if (seed->type != Json::OBJECT) fail("config field seed must be an object");
        const Json *v = findField(*seed, "output_length");
        if (v) cfg.seed.outputLength = static_cast<int>(parseSizeTDecimal(integerTextFromJson(*v, "seed.output_length"), "seed.output_length"));
        v = findField(*seed, "seed_file");
        if (v) {
            if (v->type != Json::STRING) fail("seed.seed_file must be a string");
            cfg.seed.seedFile = v->s;
        }
        v = findField(*seed, "basis_output_path");
        if (v) {
            if (v->type != Json::STRING) fail("seed.basis_output_path must be a string");
            cfg.seed.basisOut = v->s;
        }
        v = findField(*seed, "mode");
        if (v) {
            if (v->type != Json::STRING) fail("seed.mode must be strict or wrap");
            cfg.seed.mode = v->s;
        }
        v = findField(*seed, "basis_policy");
        if (v) {
            if (v->type != Json::STRING) fail("seed.basis_policy must be a string");
            cfg.seed.basisPolicy = v->s;
        }
        v = findField(*seed, "emit_generated_seed");
        if (v) {
            if (v->type != Json::BOOL) fail("seed.emit_generated_seed must be boolean");
            cfg.seed.emitGeneratedSeed = v->b;
        }
    }
    if (cfg.seed.outputLength < 1 || cfg.seed.outputLength > 6) fail("seed.output_length must be in 1..6");
    if (cfg.seed.mode != "strict" && cfg.seed.mode != "wrap") fail("seed.mode must be strict or wrap");
    if (cfg.seed.basisPolicy != "ordered_with_repetition") {
        fail("unsupported seed.basis_policy '" + cfg.seed.basisPolicy + "'; only ordered_with_repetition is implemented");
    }
    const Json *out = findField(root, "output");
    if (out) {
        if (out->type != Json::OBJECT) fail("config field output must be an object");
        const Json *v = findField(*out, "format");
        if (v) {
            if (v->type != Json::STRING) fail("output.format must be a string");
            cfg.output.format = v->s;
        }
        v = findField(*out, "path");
        if (v) {
            if (v->type != Json::STRING) fail("output.path must be a string");
            cfg.output.path = v->s;
        }
    }
    return cfg;
}

static string readFile(const string &path) {
    FILE *f = std::fopen(path.c_str(), "rb");
    if (!f) fail("cannot open file for reading: " + path);
    string data;
    char buf[8192];
    while (true) {
        size_t n = std::fread(buf, 1, sizeof(buf), f);
        if (n) data.append(buf, n);
        if (n < sizeof(buf)) {
            if (std::ferror(f)) {
                std::fclose(f);
                fail("error reading file: " + path);
            }
            break;
        }
    }
    if (std::fclose(f) != 0) fail("error closing read file: " + path);
    return data;
}

static void writeFile(const string &path, const string &text, bool append = false) {
    FILE *f = std::fopen(path.c_str(), append ? "ab" : "wb");
    if (!f) fail("cannot open file for writing: " + path);
    if (!text.empty()) {
        size_t n = std::fwrite(text.data(), 1, text.size(), f);
        if (n != text.size()) {
            std::fclose(f);
            fail("short write while writing file: " + path);
        }
    }
    if (std::fclose(f) != 0) fail("error closing written file: " + path);
}

static Config readConfigFile(const string &path) {
    return parseConfigText(readFile(path), path);
}

static string decodeInteractiveEscapes(const string &line, const string &where) {
    string out;
    for (size_t i = 0; i < line.size(); ++i) {
        char c = line[i];
        if (c != '\\') {
            out.push_back(c);
            continue;
        }
        if (++i >= line.size()) fail("malformed escaped input at " + where + ": trailing backslash");
        char e = line[i];
        switch (e) {
            case 'n': out.push_back('\n'); break;
            case 'r': out.push_back('\r'); break;
            case 't': out.push_back('\t'); break;
            case 's': out.push_back(' '); break;
            case '\\': out.push_back('\\'); break;
            case '"': out.push_back('"'); break;
            case 'x': {
                if (i + 2 >= line.size()) fail("malformed escaped input at " + where + ": incomplete \\xHH escape");
                int a = std::isxdigit(static_cast<unsigned char>(line[i + 1])) ? 1 : 0;
                int b = std::isxdigit(static_cast<unsigned char>(line[i + 2])) ? 1 : 0;
                if (!a || !b) fail("malformed escaped input at " + where + ": invalid \\xHH escape");
                string hx = line.substr(i + 1, 2);
                unsigned int val = 0;
                std::istringstream is(hx);
                is >> std::hex >> val;
                out.push_back(static_cast<char>(val));
                i += 2;
                break;
            }
            default:
                fail("malformed escaped input at " + where + ": unsupported escape \\" + string(1, e));
        }
    }
    return out;
}

static ComponentValue encodeComponent(const ComponentSpec &c, const string &input, size_t instanceIndex) {
    ComponentValue v;
    v.input = input;
    v.charLength = input.size();
    v.preview = safePreview(input);
    std::set<unsigned char> uniq;
    for (size_t i = 0; i < input.size(); ++i) uniq.insert(static_cast<unsigned char>(input[i]));
    v.uniqueCount = uniq.size();
    for (std::set<unsigned char>::const_iterator it = uniq.begin(); it != uniq.end(); ++it) v.uniqueSymbols.push_back(escapeByte(*it));

    size_t L = input.size();
    if (c.mode == FIXED) {
        if (L != c.fixed) fail("instance " + std::to_string(instanceIndex) + " component " + c.name +
                               " has wrong fixed byte length " + std::to_string(L) +
                               "; expected " + std::to_string(c.fixed));
    } else {
        if (L < c.minLen || L > c.maxLen) fail("instance " + std::to_string(instanceIndex) + " component " + c.name +
                                               " byte length " + std::to_string(L) + " outside allowed interval [" +
                                               std::to_string(c.minLen) + "," + std::to_string(c.maxLen) + "]");
    }
    const uint32_t r = static_cast<uint32_t>(c.alphabet.size());
    BigUInt id(0);
    for (size_t k = 0; k < input.size(); ++k) {
        unsigned char b = static_cast<unsigned char>(input[k]);
        int digit = c.byteIndex[b];
        if (digit < 0) fail("instance " + std::to_string(instanceIndex) + " component " + c.name +
                            " contains byte outside alphabet: " + escapeByte(b));
        id = id.mulSmall(r);
        id.addSmall(static_cast<uint32_t>(digit));
    }
    if (c.mode == VARIABLE) {
        BigUInt offset(0);
        BigUInt br(r);
        for (size_t ell = c.minLen; ell < L; ++ell) offset = offset + powUInt(br, ell);
        id = offset + id;
    }
    if (!(id < c.domain)) fail("internal encoder produced id outside domain for component " + c.name);
    v.rawId = id;
    v.modulus = c.modulus;
    v.residue = id.mod(c.modulus);
    v.canonical = input;
    return v;
}

static string decodeFixedOrdinal(const ComponentSpec &c, const BigUInt &ordinal, size_t L) {
    const uint32_t r = static_cast<uint32_t>(c.alphabet.size());
    BigUInt n = ordinal;
    string out(L, '\0');
    for (size_t pos = L; pos-- > 0;) {
        uint32_t rem = 0;
        n = n.divSmall(r, &rem);
        if (rem >= c.alphabet.size()) fail("internal decode remainder outside alphabet");
        out[pos] = c.alphabet[rem];
    }
    if (!n.isZero()) fail("internal fixed ordinal decode overflow for component " + c.name);
    return out;
}

static string decodeComponentId(const ComponentSpec &c, const BigUInt &id) {
    if (!(id < c.domain)) fail("cannot decode component " + c.name + " id outside raw domain");
    if (c.mode == FIXED) return decodeFixedOrdinal(c, id, c.fixed);
    const uint32_t r = static_cast<uint32_t>(c.alphabet.size());
    BigUInt br(r);
    BigUInt offset(0);
    for (size_t L = c.minLen; L <= c.maxLen; ++L) {
        BigUInt block = powUInt(br, L);
        BigUInt next = offset + block;
        if (id < next) return decodeFixedOrdinal(c, id - offset, L);
        offset = next;
        if (L == std::numeric_limits<size_t>::max()) break;
    }
    fail("internal variable-length decode failed for component " + c.name);
    return "";
}

static ScalarInfo classifyScalar(const vector<ComponentValue> &vals) {
    ScalarInfo s;
    s.P = BigInt::zigzag(vals[0].rawId);
    s.Q = vals[1].rawId + BigUInt(1);
    s.M = BigInt::zigzag(vals[2].rawId);
    s.G = vals[3].rawId + BigUInt(1);
    s.Alpha = BigInt::zigzag(vals[4].rawId);
    s.Beta = vals[5].rawId + BigUInt(1);
    BigUInt g = gcdUInt(s.Alpha.mag, s.Beta);
    if (g.isZero()) g = BigUInt(1);
    s.AlphaReduced = s.Alpha.divExactPositive(g);
    s.BetaReduced = s.Beta.div(g);
    s.expression = "(" + s.P.str() + " / " + s.Q.str() + ") * ((" + s.M.str() + " / " + s.G.str() +
                   ") ^ (" + s.Alpha.str() + " / " + s.Beta.str() + "))";
    if (s.M.sign == 0) {
        if (s.Alpha.sign <= 0) s.status = "undefined_real_expression";
        else s.status = "real_exact_symbolic";
    } else if (s.M.sign > 0) {
        s.status = "real_exact_symbolic";
    } else {
        s.status = s.BetaReduced.isOdd() ? "real_exact_symbolic" : "complex_required";
    }
    return s;
}

static BigUInt rankRow(const vector<ComponentSpec> &components, const vector<BigUInt> &ids) {
    BigUInt j = ids[0];
    for (size_t i = 1; i < 6; ++i) {
        j = j * components[i].domain;
        j = j + ids[i];
    }
    return j;
}

static vector<BigUInt> unrankRow(const vector<ComponentSpec> &components, const BigUInt &rowOrdinal) {
    BigUInt work = rowOrdinal;
    vector<BigUInt> ids(6);
    for (size_t ri = 6; ri-- > 1;) {
        std::pair<BigUInt, BigUInt> qr = BigUInt::divmod(work, components[ri].domain);
        ids[ri] = qr.second;
        work = qr.first;
    }
    ids[0] = work;
    if (!(ids[0] < components[0].domain)) fail("row ordinal outside row universe during unranking");
    return ids;
}

static BigUInt rowSpaceSize(const vector<ComponentSpec> &components) {
    BigUInt r(1);
    for (size_t i = 0; i < components.size(); ++i) r = r * components[i].domain;
    return r;
}

static BigUInt rankBasis(const vector<BigUInt> &rowOrdinals, const BigUInt &R) {
    BigUInt k(0);
    for (size_t i = 0; i < rowOrdinals.size(); ++i) {
        k = k * R;
        k = k + rowOrdinals[i];
    }
    return k;
}

static vector<BigUInt> unrankBasis(const BigUInt &address, const BigUInt &R, size_t N) {
    vector<BigUInt> rows(N);
    BigUInt work = address;
    for (size_t i = N; i-- > 0;) {
        std::pair<BigUInt, BigUInt> qr = BigUInt::divmod(work, R);
        rows[i] = qr.second;
        work = qr.first;
    }
    if (!work.isZero()) fail("basis address outside basis address space during unranking");
    return rows;
}

static BigUInt basisSpaceSize(const BigUInt &R, size_t N) {
    return powUInt(R, N);
}

static vector<BigUInt> encodeSeed(const BigUInt &K, const BigUInt &W, int k) {
    vector<BigUInt> seed(static_cast<size_t>(k));
    BigUInt work = K;
    for (int i = k - 1; i >= 0; --i) {
        std::pair<BigUInt, BigUInt> qr = BigUInt::divmod(work, W);
        seed[static_cast<size_t>(i)] = qr.second;
        work = qr.first;
    }
    if (!work.isZero()) fail("internal seed encoding overflow");
    return seed;
}

static BigUInt decodeSeedPolynomial(const vector<BigUInt> &seed, const BigUInt &W) {
    BigUInt k(0);
    for (size_t i = 0; i < seed.size(); ++i) {
        k = k * W;
        k = k + seed[i];
    }
    return k;
}

static InstanceResult makeInstanceFromStrings(const vector<ComponentSpec> &components, const map<string, string> &in, size_t idx) {
    InstanceResult r;
    for (size_t i = 0; i < 6; ++i) {
        map<string, string>::const_iterator it = in.find(components[i].name);
        if (it == in.end()) fail("instance " + std::to_string(idx) + " missing component " + components[i].name);
        ComponentValue cv = encodeComponent(components[i], it->second, idx);
        if (isSignedSlot(i)) {
            cv.mappedSigned = BigInt::zigzag(cv.rawId);
            cv.mappedValue = cv.mappedSigned.str();
        } else {
            cv.mappedPositive = cv.rawId + BigUInt(1);
            cv.mappedValue = cv.mappedPositive.str();
        }
        r.comp.push_back(cv);
    }
    vector<BigUInt> ids;
    for (size_t i = 0; i < 6; ++i) ids.push_back(r.comp[i].rawId);
    r.scalar = classifyScalar(r.comp);
    r.rowOrdinal = rankRow(components, ids);
    return r;
}

static InstanceResult makeInstanceFromIds(const vector<ComponentSpec> &components, const vector<BigUInt> &ids, size_t idx) {
    map<string, string> m;
    for (size_t i = 0; i < 6; ++i) m[components[i].name] = decodeComponentId(components[i], ids[i]);
    InstanceResult r = makeInstanceFromStrings(components, m, idx);
    for (size_t i = 0; i < 6; ++i) {
        if (r.comp[i].rawId != ids[i]) fail("canonical reconstructed string failed round-trip for component " + components[i].name);
    }
    return r;
}

static vector<InstanceResult> processInlineInstances(const Config &cfg) {
    if (cfg.instances.size() != cfg.instanceCount) {
        fail("instance_count mismatch: expected " + std::to_string(cfg.instanceCount) +
             " instances but found " + std::to_string(cfg.instances.size()));
    }
    vector<InstanceResult> out;
    for (size_t i = 0; i < cfg.instances.size(); ++i) out.push_back(makeInstanceFromStrings(cfg.components, cfg.instances[i], i));
    return out;
}

static string jsonBig(const BigUInt &v) { return jsonEscape(v.str()); }
static string jsonBigInt(const BigInt &v) { return jsonEscape(v.str()); }

static void jsonBigArray(std::ostringstream &out, const vector<BigUInt> &v) {
    out << "[";
    for (size_t i = 0; i < v.size(); ++i) {
        if (i) out << ",";
        out << jsonBig(v[i]);
    }
    out << "]";
}

static string generateJsonOutput(const Config &cfg, const vector<InstanceResult> &instances, bool timestampRequested) {
    BigUInt R = rowSpaceSize(cfg.components);
    BigUInt S = basisSpaceSize(R, cfg.instanceCount);
    BigUInt W = kthRootCeil(S, cfg.seed.outputLength);
    vector<BigUInt> rows;
    for (size_t i = 0; i < instances.size(); ++i) rows.push_back(instances[i].rowOrdinal);
    BigUInt K = rankBasis(rows, R);
    vector<BigUInt> seed = encodeSeed(K, W, cfg.seed.outputLength);
    std::ostringstream out;
    out << "{\n";
    out << "  \"metadata\": {\n";
    out << "    \"program\": \"16.cpp deterministic basis-tensor generator\",\n";
    out << "    \"config_path\": " << jsonEscape(cfg.path) << ",\n";
    out << "    \"symbol_mode\": \"byte-symbol mode; alphabets and input lengths are decoded bytes\",\n";
    out << "    \"component_order\": [\"p\",\"q\",\"m\",\"g\",\"alpha\",\"beta\"],\n";
    out << "    \"raw_dataset_name\": \"B_raw\",\n";
    out << "    \"residue_dataset_name\": \"B_residue\",\n";
    out << "    \"basis_wording\": \"basis tensor dataset refers to B_raw and B_residue together unless qualified; no linear algebra independence is claimed\",\n";
    out << "    \"finite_seed_scope\": \"A finite 17.txt configuration creates a finite raw row space and finite basis-address space; one finite run does not generate uncountable objects exactly\",\n";
    out << "    \"timestamps_enabled\": " << (timestampRequested ? "true" : "false");
    if (timestampRequested) {
        std::time_t t = std::time(nullptr);
        out << ",\n    \"timestamp_note\": \"nondeterministic timestamp metadata was requested\",\n";
        out << "    \"timestamp_unix\": " << jsonEscape(std::to_string(static_cast<long long>(t))) << "\n";
    } else {
        out << "\n";
    }
    out << "  },\n";
    out << "  \"component_domains\": [\n";
    for (size_t i = 0; i < cfg.components.size(); ++i) {
        const ComponentSpec &c = cfg.components[i];
        if (i) out << ",\n";
        out << "    {\"name\":" << jsonEscape(c.name)
            << ",\"alphabet_size\":\"" << c.alphabet.size() << "\""
            << ",\"length_policy\":";
        if (c.mode == FIXED) out << "{\"mode\":\"fixed\",\"value\":\"" << c.fixed << "\"}";
        else out << "{\"mode\":\"variable\",\"min\":\"" << c.minLen << "\",\"max\":\"" << c.maxLen << "\"}";
        out << ",\"raw_domain_size\":" << jsonBig(c.domain)
            << ",\"selected_residue_modulus\":" << jsonBig(c.modulus) << "}";
    }
    out << "\n  ],\n";
    out << "  \"instances\": [\n";
    for (size_t i = 0; i < instances.size(); ++i) {
        if (i) out << ",\n";
        const InstanceResult &ir = instances[i];
        out << "    {\n";
        out << "      \"index\": \"" << i << "\",\n";
        out << "      \"components\": [\n";
        for (size_t c = 0; c < 6; ++c) {
            if (c) out << ",\n";
            const ComponentValue &v = ir.comp[c];
            out << "        {\"name\":" << jsonEscape(cfg.components[c].name)
                << ",\"input_string\":" << jsonEscape(v.input)
                << ",\"char_length\":" << v.charLength
                << ",\"unique_count\":" << v.uniqueCount
                << ",\"unique_symbols\":[";
            for (size_t u = 0; u < v.uniqueSymbols.size(); ++u) {
                if (u) out << ",";
                out << jsonEscape(v.uniqueSymbols[u]);
            }
            out << "],\"preview\":" << jsonEscape(v.preview)
                << ",\"raw_id\":" << jsonBig(v.rawId)
                << ",\"selected_residue_modulus\":" << jsonBig(v.modulus)
                << ",\"least_residue\":" << jsonBig(v.residue)
                << ",\"mapped_structure1_parameter\":" << jsonEscape(v.mappedValue)
                << "}";
        }
        out << "\n      ],\n";
        out << "      \"structure1_scalar\": {\n";
        out << "        \"p\":" << jsonBigInt(ir.scalar.P) << ", \"q\":" << jsonBig(ir.scalar.Q)
            << ", \"m\":" << jsonBigInt(ir.scalar.M) << ", \"g\":" << jsonBig(ir.scalar.G)
            << ", \"alpha\":" << jsonBigInt(ir.scalar.Alpha) << ", \"beta\":" << jsonBig(ir.scalar.Beta) << ",\n";
        out << "        \"reduced_exponent\": {\"alpha\":" << jsonBigInt(ir.scalar.AlphaReduced)
            << ",\"beta\":" << jsonBig(ir.scalar.BetaReduced) << "},\n";
        out << "        \"symbolic_expression\": " << jsonEscape("a_" + std::to_string(i) + " = " + ir.scalar.expression) << ",\n";
        out << "        \"real_admissibility_status\": " << jsonEscape(ir.scalar.status) << "\n";
        out << "      },\n";
        out << "      \"row_ordinal\": " << jsonBig(ir.rowOrdinal) << "\n";
        out << "    }";
    }
    out << "\n  ],\n";
    out << "  \"B_raw\": [";
    for (size_t i = 0; i < instances.size(); ++i) {
        if (i) out << ",";
        out << "[";
        for (size_t c = 0; c < 6; ++c) {
            if (c) out << ",";
            out << jsonBig(instances[i].comp[c].rawId);
        }
        out << "]";
    }
    out << "],\n";
    out << "  \"B_residue\": [";
    for (size_t i = 0; i < instances.size(); ++i) {
        if (i) out << ",";
        out << "[";
        for (size_t c = 0; c < 6; ++c) {
            if (c) out << ",";
            out << jsonBig(instances[i].comp[c].residue);
        }
        out << "]";
    }
    out << "],\n";
    out << "  \"seed_metadata\": {\n";
    out << "    \"basis_policy\": \"ordered_with_repetition\",\n";
    out << "    \"basis_row_count\": " << jsonEscape(std::to_string(cfg.instanceCount)) << ",\n";
    out << "    \"row_space_size\": " << jsonBig(R) << ",\n";
    out << "    \"basis_address_space_size\": " << jsonBig(S) << ",\n";
    out << "    \"seed_length\": " << jsonEscape(std::to_string(cfg.seed.outputLength)) << ",\n";
    out << "    \"seed_radix\": " << jsonBig(W) << ",\n";
    out << "    \"basis_address\": " << jsonBig(K) << ",\n";
    out << "    \"canonical_seed_sequence\": ";
    jsonBigArray(out, seed);
    out << ",\n";
    out << "    \"addresses_dataset\": \"B_raw\",\n";
    out << "    \"residue_dataset\": \"B_residue\"\n";
    out << "  }\n";
    out << "}\n";
    return out.str();
}

static string generateTextOutput(const Config &cfg, const vector<InstanceResult> &instances, bool timestampRequested) {
    BigUInt R = rowSpaceSize(cfg.components);
    BigUInt S = basisSpaceSize(R, cfg.instanceCount);
    BigUInt W = kthRootCeil(S, cfg.seed.outputLength);
    vector<BigUInt> rows;
    for (size_t i = 0; i < instances.size(); ++i) rows.push_back(instances[i].rowOrdinal);
    BigUInt K = rankBasis(rows, R);
    vector<BigUInt> seed = encodeSeed(K, W, cfg.seed.outputLength);
    std::ostringstream out;
    out << "16.cpp deterministic basis-tensor generator\n";
    out << "Configuration: " << cfg.path << "\n";
    out << "Symbol mode: byte-symbol mode; alphabets and input lengths are decoded bytes.\n";
    out << "Component order: p, q, m, g, alpha, beta\n";
    out << "Dataset names: B_raw (reconstruction-addressed raw tensor dataset), B_residue (least-residue tensor dataset)\n";
    out << "No linear algebra independence is claimed; this is a basis-tensor candidate set.\n";
    out << "Finite scope: a finite 17.txt configuration creates a finite raw row space and finite basis-address space.\n";
    out << "Timestamps enabled: " << (timestampRequested ? "true (nondeterministic timestamp metadata requested)" : "false") << "\n";
    if (timestampRequested) out << "Timestamp unix: " << static_cast<long long>(std::time(nullptr)) << "\n";
    out << "\nComponent domains:\n";
    for (size_t i = 0; i < cfg.components.size(); ++i) {
        const ComponentSpec &c = cfg.components[i];
        out << "- " << c.name << ": alphabet_size=" << c.alphabet.size();
        if (c.mode == FIXED) out << ", length=fixed(" << c.fixed << ")";
        else out << ", length=variable([" << c.minLen << "," << c.maxLen << "])";
        out << ", raw_domain_size=" << c.domain.str() << ", selected_residue_modulus=" << c.modulus.str() << "\n";
    }
    out << "\nInstances:\n";
    for (size_t i = 0; i < instances.size(); ++i) {
        const InstanceResult &ir = instances[i];
        out << "Instance " << i << ":\n";
        for (size_t c = 0; c < 6; ++c) {
            const ComponentValue &v = ir.comp[c];
            out << "  " << cfg.components[c].name
                << ": input=" << jsonEscape(v.input)
                << ", char_length=" << v.charLength
                << ", unique_count=" << v.uniqueCount
                << ", preview=" << jsonEscape(v.preview)
                << ", raw_id=" << v.rawId.str()
                << ", modulus=" << v.modulus.str()
                << ", least_residue=" << v.residue.str()
                << ", mapped_parameter=" << v.mappedValue << "\n";
        }
        out << "  scalar_expression: a_" << i << " = " << ir.scalar.expression << "\n";
        out << "  real_admissibility_status: " << ir.scalar.status << "\n";
        out << "  row_ordinal: " << ir.rowOrdinal.str() << "\n";
    }
    out << "\nB_raw rows:\n";
    for (size_t i = 0; i < instances.size(); ++i) {
        out << "  [";
        for (size_t c = 0; c < 6; ++c) {
            if (c) out << ", ";
            out << instances[i].comp[c].rawId.str();
        }
        out << "]\n";
    }
    out << "B_residue rows:\n";
    for (size_t i = 0; i < instances.size(); ++i) {
        out << "  [";
        for (size_t c = 0; c < 6; ++c) {
            if (c) out << ", ";
            out << instances[i].comp[c].residue.str();
        }
        out << "]\n";
    }
    out << "\nSeed metadata:\n";
    out << "  basis_policy=ordered_with_repetition\n";
    out << "  basis_row_count=" << cfg.instanceCount << "\n";
    out << "  row_space_size=" << R.str() << "\n";
    out << "  basis_address_space_size=" << S.str() << "\n";
    out << "  seed_length=" << cfg.seed.outputLength << "\n";
    out << "  seed_radix=" << W.str() << "\n";
    out << "  basis_address=" << K.str() << "\n";
    out << "  canonical_seed_sequence=[";
    for (size_t i = 0; i < seed.size(); ++i) {
        if (i) out << ", ";
        out << seed[i].str();
    }
    out << "]\n";
    out << "  seed sequence addresses B_raw; it is metadata, not a tensor coordinate.\n";
    return out.str();
}

static vector<BigUInt> parseSeedLine(const string &line, size_t lineNo) {
    string s = trim(line);
    if (s.empty()) return vector<BigUInt>();
    if (s[0] == '#') return vector<BigUInt>();
    if (s.front() == '[') {
        if (s.back() != ']') fail("invalid seed syntax on line " + std::to_string(lineNo) + ": missing closing bracket");
        s = s.substr(1, s.size() - 2);
    }
    for (size_t i = 0; i < s.size(); ++i) {
        if (s[i] == ',') s[i] = ' ';
    }
    std::istringstream is(s);
    vector<BigUInt> out;
    string tok;
    while (is >> tok) {
        if (!tok.empty() && tok[0] == '-') fail("invalid seed syntax on line " + std::to_string(lineNo) + ": negative seed integer");
        out.push_back(BigUInt::fromDecimal(tok, "seed line " + std::to_string(lineNo)));
    }
    if (out.empty()) return out;
    if (out.size() > 6) fail("invalid seed syntax on line " + std::to_string(lineNo) + ": more than 6 integers");
    return out;
}

struct SeedRecordResult {
    string sourceLine;
    size_t lineNumber = 0;
    vector<BigUInt> seed;
    int k = 0;
    BigUInt W;
    BigUInt decoded;
    BigUInt effective;
    bool wrapped = false;
    vector<BigUInt> rows;
    vector<InstanceResult> instances;
};

static SeedRecordResult buildOneSeedRecord(const Config &cfg, const string &line, size_t lineNo, const vector<BigUInt> &seed) {
    SeedRecordResult rr;
    rr.sourceLine = line;
    rr.lineNumber = lineNo;
    rr.seed = seed;
    rr.k = static_cast<int>(seed.size());
    BigUInt R = rowSpaceSize(cfg.components);
    BigUInt S = basisSpaceSize(R, cfg.instanceCount);
    rr.W = kthRootCeil(S, rr.k);
    rr.decoded = decodeSeedPolynomial(seed, rr.W);
    if (cfg.seed.mode == "strict") {
        for (size_t i = 0; i < seed.size(); ++i) {
            if (!(seed[i] < rr.W)) {
                fail("strict seed validation failed on line " + std::to_string(lineNo) +
                     ": seed digit " + std::to_string(i) + " is outside radix " + rr.W.str());
            }
        }
        if (!(rr.decoded < S)) {
            fail("strict seed validation failed on line " + std::to_string(lineNo) +
                 ": decoded address " + rr.decoded.str() + " is outside [0," + (S - BigUInt(1)).str() + "]");
        }
        rr.effective = rr.decoded;
    } else {
        rr.effective = rr.decoded.mod(S);
        rr.wrapped = rr.effective != rr.decoded;
    }
    rr.rows = unrankBasis(rr.effective, R, cfg.instanceCount);
    for (size_t i = 0; i < rr.rows.size(); ++i) {
        vector<BigUInt> ids = unrankRow(cfg.components, rr.rows[i]);
        rr.instances.push_back(makeInstanceFromIds(cfg.components, ids, i));
    }
    return rr;
}

static string seedRecordJsonBlock(const Config &cfg, const SeedRecordResult &rr) {
    std::ostringstream out;
    out << "{\n";
    out << "      \"source_seed_sequence\": ";
    jsonBigArray(out, rr.seed);
    out << ",\n";
    out << "      \"source_seed_line\": " << jsonEscape(rr.sourceLine) << ",\n";
    out << "      \"source_seed_line_number\": " << jsonEscape(std::to_string(rr.lineNumber)) << ",\n";
    out << "      \"seed_length\": " << jsonEscape(std::to_string(rr.k)) << ",\n";
    out << "      \"seed_radix\": " << jsonBig(rr.W) << ",\n";
    out << "      \"decoded_seed_address\": " << jsonBig(rr.decoded) << ",\n";
    out << "      \"effective_basis_address\": " << jsonBig(rr.effective) << ",\n";
    out << "      \"seed_wrapped\": " << (rr.wrapped ? "true" : "false") << ",\n";
    out << "      \"row_ordinals\": ";
    jsonBigArray(out, rr.rows);
    out << ",\n";
    out << "      \"canonical_component_strings\": [";
    for (size_t i = 0; i < rr.instances.size(); ++i) {
        if (i) out << ",";
        out << "{";
        for (size_t c = 0; c < 6; ++c) {
            if (c) out << ",";
            out << jsonEscape(cfg.components[c].name) << ":" << jsonEscape(rr.instances[i].comp[c].input);
        }
        out << "}";
    }
    out << "],\n";
    out << "      \"raw_basis_tensor_dataset\": [";
    for (size_t i = 0; i < rr.instances.size(); ++i) {
        if (i) out << ",";
        out << "[";
        for (size_t c = 0; c < 6; ++c) {
            if (c) out << ",";
            out << jsonBig(rr.instances[i].comp[c].rawId);
        }
        out << "]";
    }
    out << "],\n";
    out << "      \"residue_basis_tensor_dataset\": [";
    for (size_t i = 0; i < rr.instances.size(); ++i) {
        if (i) out << ",";
        out << "[";
        for (size_t c = 0; c < 6; ++c) {
            if (c) out << ",";
            out << jsonBig(rr.instances[i].comp[c].residue);
        }
        out << "]";
    }
    out << "]\n";
    out << "    }";
    return out.str();
}

static string generateSeedBuildText(const Config &cfg, const vector<SeedRecordResult> &records, bool timestampRequested) {
    BigUInt R = rowSpaceSize(cfg.components);
    BigUInt S = basisSpaceSize(R, cfg.instanceCount);
    std::set<int> ks;
    for (size_t i = 0; i < records.size(); ++i) ks.insert(records[i].k);
    std::ostringstream out;
    out << "20.txt deterministic seed-build output\n";
    out << "Configuration: " << cfg.path << "\n";
    out << "Component order: p, q, m, g, alpha, beta\n";
    out << "Symbol mode: byte-symbol mode; alphabets and input lengths are decoded bytes.\n";
    out << "Basis policy: ordered_with_repetition\n";
    out << "Seed mode: " << cfg.seed.mode << "\n";
    out << "Basis row count N: " << cfg.instanceCount << "\n";
    out << "Raw row-space size R: " << R.str() << "\n";
    out << "Basis-address-space size S: " << S.str() << "\n";
    out << "Timestamps enabled: " << (timestampRequested ? "true (nondeterministic timestamp metadata requested)" : "false") << "\n";
    if (timestampRequested) out << "Timestamp unix: " << static_cast<long long>(std::time(nullptr)) << "\n";
    out << "Component raw domain sizes and residue moduli:\n";
    for (size_t i = 0; i < cfg.components.size(); ++i) {
        out << "  " << cfg.components[i].name << ": M_c=" << cfg.components[i].domain.str()
            << ", mu_c=" << cfg.components[i].modulus.str() << "\n";
    }
    out << "Seed radices encountered:\n";
    for (std::set<int>::const_iterator it = ks.begin(); it != ks.end(); ++it) {
        out << "  k=" << *it << ", W_k=" << kthRootCeil(S, *it).str() << "\n";
    }
    out << "\n";
    for (size_t r = 0; r < records.size(); ++r) {
        const SeedRecordResult &rr = records[r];
        out << "===== BASIS BLOCK " << r << " =====\n";
        out << "source_seed_line_number: " << rr.lineNumber << "\n";
        out << "source_seed_line: " << rr.sourceLine << "\n";
        out << "parsed_seed_sequence: [";
        for (size_t i = 0; i < rr.seed.size(); ++i) {
            if (i) out << ", ";
            out << rr.seed[i].str();
        }
        out << "]\n";
        out << "seed_length: " << rr.k << "\n";
        out << "seed_radix: " << rr.W.str() << "\n";
        out << "decoded_basis_address_K_seed: " << rr.decoded.str() << "\n";
        out << "effective_basis_address_K: " << rr.effective.str() << "\n";
        out << "seed_wrapped: " << (rr.wrapped ? "true" : "false") << "\n";
        out << "row_ordinals: [";
        for (size_t i = 0; i < rr.rows.size(); ++i) {
            if (i) out << ", ";
            out << rr.rows[i].str();
        }
        out << "]\n";
        for (size_t i = 0; i < rr.instances.size(); ++i) {
            const InstanceResult &ir = rr.instances[i];
            out << "  Row " << i << ":\n";
            out << "    canonical_component_strings: ";
            for (size_t c = 0; c < 6; ++c) {
                if (c) out << ", ";
                out << cfg.components[c].name << "=" << jsonEscape(ir.comp[c].input);
            }
            out << "\n";
            out << "    raw_ids: [";
            for (size_t c = 0; c < 6; ++c) {
                if (c) out << ", ";
                out << ir.comp[c].rawId.str();
            }
            out << "]\n";
            out << "    residue_moduli: [";
            for (size_t c = 0; c < 6; ++c) {
                if (c) out << ", ";
                out << ir.comp[c].modulus.str();
            }
            out << "]\n";
            out << "    least_residues: [";
            for (size_t c = 0; c < 6; ++c) {
                if (c) out << ", ";
                out << ir.comp[c].residue.str();
            }
            out << "]\n";
            out << "    mapped_structure1_parameters: P=" << ir.scalar.P.str()
                << ", Q=" << ir.scalar.Q.str()
                << ", M=" << ir.scalar.M.str()
                << ", G=" << ir.scalar.G.str()
                << ", Alpha=" << ir.scalar.Alpha.str()
                << ", Beta=" << ir.scalar.Beta.str() << "\n";
            out << "    symbolic_scalar_expression: a_" << i << " = " << ir.scalar.expression << "\n";
            out << "    real_admissibility_status: " << ir.scalar.status << "\n";
        }
        out << "B_raw: [";
        for (size_t i = 0; i < rr.instances.size(); ++i) {
            if (i) out << ", ";
            out << "[";
            for (size_t c = 0; c < 6; ++c) {
                if (c) out << ", ";
                out << rr.instances[i].comp[c].rawId.str();
            }
            out << "]";
        }
        out << "]\n";
        out << "B_residue: [";
        for (size_t i = 0; i < rr.instances.size(); ++i) {
            if (i) out << ", ";
            out << "[";
            for (size_t c = 0; c < 6; ++c) {
                if (c) out << ", ";
                out << rr.instances[i].comp[c].residue.str();
            }
            out << "]";
        }
        out << "]\n";
        out << "seed_sequence_note: seed addresses B_raw and is metadata, not a tensor coordinate.\n\n";
        out << "parse_observable_json_block:\n";
        out << seedRecordJsonBlock(cfg, rr) << "\n\n";
    }
    return out.str();
}

static vector<SeedRecordResult> buildFromSeedFile(const Config &cfg, const string &seedPath) {
    std::istringstream in(readFile(seedPath));
    vector<SeedRecordResult> records;
    string line;
    size_t lineNo = 0;
    while (std::getline(in, line)) {
        ++lineNo;
        if (!line.empty() && line.back() == '\r') line.pop_back();
        vector<BigUInt> seed = parseSeedLine(line, lineNo);
        if (seed.empty()) continue;
        records.push_back(buildOneSeedRecord(cfg, line, lineNo, seed));
    }
    return records;
}

static string sampleConfig() {
    return
"{\n"
"  \"version\": 1,\n"
"  \"instance_count\": 2,\n"
"  \"components\": {\n"
"    \"p\": {\"alphabet\": \"0123456789\", \"length\": {\"mode\": \"fixed\", \"value\": 3}, \"signed_mapping\": \"zigzag\"},\n"
"    \"q\": {\"alphabet\": \"0123456789\", \"length\": {\"mode\": \"fixed\", \"value\": 2}, \"positive_mapping\": \"id_plus_one\"},\n"
"    \"m\": {\"alphabet\": \"01\", \"length\": {\"mode\": \"variable\", \"min\": 1, \"max\": 4}, \"signed_mapping\": \"zigzag\"},\n"
"    \"g\": {\"alphabet\": \"abc\", \"length\": {\"mode\": \"fixed\", \"value\": 2}, \"positive_mapping\": \"id_plus_one\"},\n"
"    \"alpha\": {\"alphabet\": \"xyz\", \"length\": {\"mode\": \"fixed\", \"value\": 2}, \"signed_mapping\": \"zigzag\"},\n"
"    \"beta\": {\"alphabet\": \"01\", \"length\": {\"mode\": \"fixed\", \"value\": 3}, \"positive_mapping\": \"id_plus_one\"}\n"
"  },\n"
"  \"instances\": [\n"
"    {\"p\": \"123\", \"q\": \"45\", \"m\": \"101\", \"g\": \"ab\", \"alpha\": \"xy\", \"beta\": \"011\"},\n"
"    {\"p\": \"000\", \"q\": \"01\", \"m\": \"1\", \"g\": \"cc\", \"alpha\": \"zz\", \"beta\": \"111\"}\n"
"  ],\n"
"  \"seed\": {\n"
"    \"output_length\": 1,\n"
"    \"seed_file\": \"19.txt\",\n"
"    \"basis_output_path\": \"20.txt\",\n"
"    \"mode\": \"strict\",\n"
"    \"basis_policy\": \"ordered_with_repetition\",\n"
"    \"emit_generated_seed\": true\n"
"  },\n"
"  \"output\": {\"format\": \"json\", \"path\": \"basis_tensors.json\"}\n"
"}\n";
}

static void printHelp() {
    std::cout
        << "Usage: basis_tensor [options]\n"
        << "Options:\n"
        << "  --help\n"
        << "  --config <path>          JSON configuration path (default 17.txt)\n"
        << "  --instances <N>          Override basis row count / instance_count\n"
        << "  --out <path>             Normal generation output path\n"
        << "  --interactive            Define alphabets, length policies, and strings by prompts\n"
        << "  --sample-config          Print a complete sample 17.txt JSON configuration and exit\n"
        << "  --validate-only          Validate configuration and selected inputs, then exit\n"
        << "  --json                   Emit normal output as JSON\n"
        << "  --text                   Emit normal output as text\n"
        << "  --from-seeds             Read integer seed sequences and build basis datasets\n"
        << "  --seed-file <path>       Seed sequence input path (default/config seed_file or 19.txt)\n"
        << "  --basis-out <path>       Seed-build text output path (default/config basis_output_path or 20.txt)\n"
        << "  --seed-length <1..6>     Canonical generated seed length in normal mode\n"
        << "  --seed-mode <strict|wrap>\n"
        << "  --write-seed-file <path> Write generated canonical seed as one 19.txt-compatible record\n"
        << "  --append-seed-file       Append instead of replacing when writing a seed file\n"
        << "  --self-test              Run built-in deterministic tests\n"
        << "  --timestamp              Include explicitly requested nondeterministic timestamp metadata\n"
        << "  --instance-file <path>   JSON array of instances, same object shape as config.instances\n"
        << "\n"
        << "This program operates in byte-symbol mode. A finite 17.txt configuration creates a finite\n"
        << "raw row space and a finite basis-address space. The seed layer exactly ranks/unranks all\n"
        << "ordered raw basis tensor datasets in that finite address space under ordered_with_repetition.\n"
        << "Larger finite configurations create larger finite address spaces. One finite run and one\n"
        << "finite seed file do not generate uncountable objects exactly.\n";
}

struct Options {
    string configPath = "17.txt";
    bool configProvided = false;
    bool help = false;
    bool sample = false;
    bool validateOnly = false;
    bool json = false;
    bool text = false;
    bool fromSeeds = false;
    bool interactive = false;
    bool selfTest = false;
    bool timestamp = false;
    bool appendSeedFile = false;
    string outPath;
    string seedFile;
    string basisOut;
    string writeSeedFile;
    string instanceFile;
    bool instancesOverride = false;
    size_t instancesN = 0;
    bool seedLengthOverride = false;
    int seedLength = 1;
    string seedMode;
};

static Options parseOptions(int argc, char **argv) {
    Options opt;
    for (int i = 1; i < argc; ++i) {
        string a = argv[i];
        auto needArg = [&](const string &name) -> string {
            if (i + 1 >= argc) fail("missing argument for " + name);
            return argv[++i];
        };
        if (a == "--help") opt.help = true;
        else if (a == "--config") { opt.configPath = needArg(a); opt.configProvided = true; }
        else if (a == "--instances") { opt.instancesOverride = true; opt.instancesN = parseSizeTDecimal(needArg(a), "--instances"); }
        else if (a == "--out") opt.outPath = needArg(a);
        else if (a == "--interactive") opt.interactive = true;
        else if (a == "--sample-config") opt.sample = true;
        else if (a == "--validate-only") opt.validateOnly = true;
        else if (a == "--json") opt.json = true;
        else if (a == "--text") opt.text = true;
        else if (a == "--from-seeds") opt.fromSeeds = true;
        else if (a == "--seed-file") opt.seedFile = needArg(a);
        else if (a == "--basis-out") opt.basisOut = needArg(a);
        else if (a == "--seed-length") {
            opt.seedLengthOverride = true;
            opt.seedLength = static_cast<int>(parseSizeTDecimal(needArg(a), "--seed-length"));
            if (opt.seedLength < 1 || opt.seedLength > 6) fail("--seed-length must be in 1..6");
        } else if (a == "--seed-mode") {
            opt.seedMode = needArg(a);
            if (opt.seedMode != "strict" && opt.seedMode != "wrap") fail("--seed-mode must be strict or wrap");
        } else if (a == "--write-seed-file") opt.writeSeedFile = needArg(a);
        else if (a == "--append-seed-file") opt.appendSeedFile = true;
        else if (a == "--self-test") opt.selfTest = true;
        else if (a == "--timestamp") opt.timestamp = true;
        else if (a == "--instance-file") opt.instanceFile = needArg(a);
        else if (a == "--approx-digits") {
            (void)needArg(a); // Accepted for CLI compatibility; this implementation emits exact symbolic values only.
        } else {
            fail("unknown option: " + a);
        }
    }
    if (opt.json && opt.text) fail("--json and --text are mutually exclusive");
    return opt;
}

static void applyOptions(Config &cfg, const Options &opt) {
    if (opt.instancesOverride) cfg.instanceCount = opt.instancesN;
    if (opt.seedLengthOverride) cfg.seed.outputLength = opt.seedLength;
    if (!opt.seedMode.empty()) cfg.seed.mode = opt.seedMode;
    if (!opt.seedFile.empty()) cfg.seed.seedFile = opt.seedFile;
    if (!opt.basisOut.empty()) cfg.seed.basisOut = opt.basisOut;
    if (!opt.outPath.empty()) cfg.output.path = opt.outPath;
    if (opt.json) cfg.output.format = "json";
    if (opt.text) cfg.output.format = "text";
    if (cfg.seed.outputLength < 1 || cfg.seed.outputLength > 6) fail("seed length must be in 1..6");
    if (cfg.seed.mode != "strict" && cfg.seed.mode != "wrap") fail("seed mode must be strict or wrap");
}

static void loadInstanceFile(Config &cfg, const string &path) {
    Json root = JsonParser(readFile(path)).parse();
    if (root.type != Json::ARRAY) fail("--instance-file must contain a JSON array of instance objects");
    cfg.instances.clear();
    cfg.inlineInstancesPresent = true;
    for (size_t i = 0; i < root.a.size(); ++i) {
        if (root.a[i].type != Json::OBJECT) fail("instance_file[" + std::to_string(i) + "] must be an object");
        map<string, string> one;
        for (int c = 0; c < 6; ++c) one[COMPONENT_NAMES[c]] = jsonStringField(root.a[i], COMPONENT_NAMES[c], "instance_file[" + std::to_string(i) + "]");
        cfg.instances.push_back(one);
    }
    if (cfg.instanceCount != 0 && cfg.instanceCount != cfg.instances.size()) {
        fail("instance_count mismatch with --instance-file: " + std::to_string(cfg.instanceCount) +
             " versus " + std::to_string(cfg.instances.size()));
    }
    cfg.instanceCount = cfg.instances.size();
}

static Config interactiveConfig(const Options &opt) {
    Config cfg;
    cfg.path = "<interactive>";
    std::cout << "Byte-symbol interactive mode. Use C-style escapes: \\n \\r \\t \\s \\\\ \\\" \\xHH.\n";
    for (int i = 0; i < 6; ++i) {
        ComponentSpec c;
        c.name = COMPONENT_NAMES[i];
        string line;
        std::cout << "Alphabet for " << c.name << ": ";
        std::getline(std::cin, line);
        c.alphabet = decodeInteractiveEscapes(line, "alphabet " + c.name);
        buildIndex(c);
        std::cout << "Length mode for " << c.name << " (fixed/variable): ";
        std::getline(std::cin, line);
        line = trim(line);
        if (line == "fixed") {
            c.mode = FIXED;
            std::cout << "Fixed byte length for " << c.name << ": ";
            std::getline(std::cin, line);
            c.fixed = parseSizeTDecimal(trim(line), "interactive fixed length " + c.name);
        } else if (line == "variable") {
            c.mode = VARIABLE;
            std::cout << "Minimum byte length for " << c.name << ": ";
            std::getline(std::cin, line);
            c.minLen = parseSizeTDecimal(trim(line), "interactive min length " + c.name);
            std::cout << "Maximum byte length for " << c.name << ": ";
            std::getline(std::cin, line);
            c.maxLen = parseSizeTDecimal(trim(line), "interactive max length " + c.name);
            if (c.minLen > c.maxLen) fail("interactive component " + c.name + " min length exceeds max length");
        } else {
            fail("interactive length mode must be fixed or variable");
        }
        c.domain = computeDomain(c.alphabet.size(), c.mode, c.fixed, c.minLen, c.maxLen);
        c.modulus = c.domain;
        cfg.components.push_back(c);
    }
    string line;
    std::cout << "Instance count N: ";
    std::getline(std::cin, line);
    cfg.instanceCount = parseSizeTDecimal(trim(line), "interactive instance count");
    for (size_t i = 0; i < cfg.instanceCount; ++i) {
        map<string, string> one;
        for (int c = 0; c < 6; ++c) {
            std::cout << "Instance " << i << " component " << COMPONENT_NAMES[c] << ": ";
            std::getline(std::cin, line);
            one[COMPONENT_NAMES[c]] = decodeInteractiveEscapes(line, "instance " + std::to_string(i) + " component " + COMPONENT_NAMES[c]);
        }
        cfg.instances.push_back(one);
    }
    cfg.inlineInstancesPresent = true;
    if (opt.seedLengthOverride) cfg.seed.outputLength = opt.seedLength;
    if (!opt.seedMode.empty()) cfg.seed.mode = opt.seedMode;
    if (!opt.outPath.empty()) cfg.output.path = opt.outPath;
    if (opt.json) cfg.output.format = "json";
    if (opt.text) cfg.output.format = "text";
    return cfg;
}

static void writeGeneratedSeedFile(const Config &cfg, const vector<InstanceResult> &instances, const string &path, bool append) {
    BigUInt R = rowSpaceSize(cfg.components);
    BigUInt S = basisSpaceSize(R, cfg.instanceCount);
    BigUInt W = kthRootCeil(S, cfg.seed.outputLength);
    vector<BigUInt> rows;
    for (size_t i = 0; i < instances.size(); ++i) rows.push_back(instances[i].rowOrdinal);
    BigUInt K = rankBasis(rows, R);
    vector<BigUInt> seed = encodeSeed(K, W, cfg.seed.outputLength);
    std::ostringstream line;
    for (size_t i = 0; i < seed.size(); ++i) {
        if (i) line << " ";
        line << seed[i].str();
    }
    line << "\n";
    writeFile(path, line.str(), append);
}

static ComponentSpec testComponent(const string &name, const string &alphabet, LengthMode mode, size_t a, size_t b = 0) {
    ComponentSpec c;
    c.name = name;
    c.alphabet = alphabet;
    c.mode = mode;
    if (mode == FIXED) c.fixed = a;
    else {
        c.minLen = a;
        c.maxLen = b;
    }
    buildIndex(c);
    c.domain = computeDomain(c.alphabet.size(), c.mode, c.fixed, c.minLen, c.maxLen);
    c.modulus = c.domain;
    return c;
}

static void requireTest(bool cond, const string &msg) {
    if (!cond) fail("self-test failed: " + msg);
}

static bool throwsAny(void (*fn)()) {
    try {
        fn();
    } catch (...) {
        return true;
    }
    return false;
}

static void testOutsideAlphabet() {
    ComponentSpec c = testComponent("p", "01", FIXED, 1);
    (void)encodeComponent(c, "2", 0);
}

static void testWrongLength() {
    ComponentSpec c = testComponent("p", "01", FIXED, 3);
    (void)encodeComponent(c, "01", 0);
}

static Config tinyConfig(size_t N) {
    Config cfg;
    cfg.path = "<self-test>";
    cfg.instanceCount = N;
    for (int i = 0; i < 6; ++i) cfg.components.push_back(testComponent(COMPONENT_NAMES[i], "01", FIXED, 1));
    return cfg;
}

static void runSelfTests() {
    {
        ComponentSpec c = testComponent("x", "01", FIXED, 3);
        requireTest(encodeComponent(c, "000", 0).rawId.str() == "0", "fixed 000 maps to 0");
        requireTest(encodeComponent(c, "001", 0).rawId.str() == "1", "fixed 001 maps to 1");
        requireTest(encodeComponent(c, "010", 0).rawId.str() == "2", "fixed 010 maps to 2");
        requireTest(encodeComponent(c, "111", 0).rawId.str() == "7", "fixed 111 maps to 7");
    }
    {
        ComponentSpec c = testComponent("x", "ab", VARIABLE, 1, 2);
        requireTest(encodeComponent(c, "a", 0).rawId.str() == "0", "variable a maps to 0");
        requireTest(encodeComponent(c, "b", 0).rawId.str() == "1", "variable b maps to 1");
        requireTest(encodeComponent(c, "aa", 0).rawId.str() == "2", "variable aa maps to 2");
        requireTest(encodeComponent(c, "ab", 0).rawId.str() == "3", "variable ab maps to 3");
        requireTest(encodeComponent(c, "ba", 0).rawId.str() == "4", "variable ba maps to 4");
        requireTest(encodeComponent(c, "bb", 0).rawId.str() == "5", "variable bb maps to 5");
    }
    requireTest(BigInt::zigzag(BigUInt(0)).str() == "0", "zigzag 0");
    requireTest(BigInt::zigzag(BigUInt(1)).str() == "1", "zigzag 1");
    requireTest(BigInt::zigzag(BigUInt(2)).str() == "-1", "zigzag 2");
    requireTest(BigInt::zigzag(BigUInt(3)).str() == "2", "zigzag 3");
    requireTest(BigInt::zigzag(BigUInt(4)).str() == "-2", "zigzag 4");
    requireTest((BigUInt(0) + BigUInt(1)).str() == "1", "positive map 0");
    requireTest((BigUInt(7) + BigUInt(1)).str() == "8", "positive map 7");
    requireTest(throwsAny(testOutsideAlphabet), "outside alphabet rejected");
    requireTest(throwsAny(testWrongLength), "wrong fixed length rejected");
    {
        vector<ComponentValue> vals(6);
        vals[0].rawId = BigUInt(0); // P=0
        vals[1].rawId = BigUInt(0); // Q=1
        vals[2].rawId = BigUInt(0); // M=0
        vals[3].rawId = BigUInt(0); // G=1
        vals[4].rawId = BigUInt(2); // Alpha=-1
        vals[5].rawId = BigUInt(0); // Beta=1
        requireTest(classifyScalar(vals).status == "undefined_real_expression", "zero base negative exponent undefined");
        vals[4].rawId = BigUInt(0);
        requireTest(classifyScalar(vals).status == "undefined_real_expression", "zero base zero exponent undefined");
        vals[4].rawId = BigUInt(1);
        requireTest(classifyScalar(vals).status == "real_exact_symbolic", "zero base positive exponent real");
        vals[2].rawId = BigUInt(2); // M=-1
        vals[4].rawId = BigUInt(1); // Alpha=1
        vals[5].rawId = BigUInt(1); // Beta=2
        requireTest(classifyScalar(vals).status == "complex_required", "negative base even denominator complex");
        vals[5].rawId = BigUInt(2); // Beta=3
        requireTest(classifyScalar(vals).status == "real_exact_symbolic", "negative base odd denominator real");
    }
    {
        Config cfg = tinyConfig(1);
        vector<BigUInt> ids;
        ids.push_back(BigUInt(0));
        ids.push_back(BigUInt(1));
        ids.push_back(BigUInt(1));
        ids.push_back(BigUInt(0));
        ids.push_back(BigUInt(1));
        ids.push_back(BigUInt(0));
        BigUInt row = rankRow(cfg.components, ids);
        vector<BigUInt> ids2 = unrankRow(cfg.components, row);
        requireTest(ids2.size() == ids.size(), "unrank row id count");
        for (size_t i = 0; i < ids.size(); ++i) {
            requireTest(ids[i] == ids2[i], "rank/unrank row ids");
            string s = decodeComponentId(cfg.components[i], ids2[i]);
            requireTest(encodeComponent(cfg.components[i], s, 0).rawId == ids[i], "canonical string round-trip");
        }
    }
    {
        BigUInt R(64), S(64), W1 = kthRootCeil(S, 1), W2 = kthRootCeil(S, 2);
        requireTest(W1.str() == "64", "W1 for S=64");
        requireTest(decodeSeedPolynomial(vector<BigUInt>(1, BigUInt(5)), W1).str() == "5", "seed [5]");
        requireTest(W2.str() == "8", "W2 for S=64");
        vector<BigUInt> s05;
        s05.push_back(BigUInt(0));
        s05.push_back(BigUInt(5));
        requireTest(decodeSeedPolynomial(s05, W2).str() == "5", "seed [0,5]");
        vector<BigUInt> s77;
        s77.push_back(BigUInt(7));
        s77.push_back(BigUInt(7));
        requireTest(decodeSeedPolynomial(s77, W2).str() == "63", "seed [7,7]");
        vector<BigUInt> s80;
        s80.push_back(BigUInt(8));
        s80.push_back(BigUInt(0));
        requireTest(!(s80[0] < W2) && !(decodeSeedPolynomial(s80, W2) < S), "strict seed [8,0] invalid");
        (void)R;
    }
    {
        BigUInt R(64), S = basisSpaceSize(R, 2), W = kthRootCeil(S, 2);
        requireTest(S.str() == "4096", "S=4096");
        requireTest(W.str() == "64", "W2=64 for S=4096");
        vector<BigUInt> s11;
        s11.push_back(BigUInt(1));
        s11.push_back(BigUInt(1));
        BigUInt K = decodeSeedPolynomial(s11, W);
        requireTest(K.str() == "65", "seed [1,1] decodes to 65");
        vector<BigUInt> rows = unrankBasis(K, R, 2);
        requireTest(rows[0].str() == "1" && rows[1].str() == "1", "address 65 unrank rows [1,1]");
    }
    {
        Config cfg = tinyConfig(2);
        cfg.seed.outputLength = 2;
        map<string, string> a, b;
        for (int i = 0; i < 6; ++i) {
            a[COMPONENT_NAMES[i]] = (i % 2 == 0) ? "0" : "1";
            b[COMPONENT_NAMES[i]] = (i % 2 == 0) ? "1" : "0";
        }
        cfg.instances.push_back(a);
        cfg.instances.push_back(b);
        vector<InstanceResult> inst = processInlineInstances(cfg);
        BigUInt R = rowSpaceSize(cfg.components);
        BigUInt S = basisSpaceSize(R, cfg.instanceCount);
        BigUInt W = kthRootCeil(S, cfg.seed.outputLength);
        vector<BigUInt> rows;
        rows.push_back(inst[0].rowOrdinal);
        rows.push_back(inst[1].rowOrdinal);
        BigUInt K = rankBasis(rows, R);
        vector<BigUInt> seed = encodeSeed(K, W, cfg.seed.outputLength);
        BigUInt K2 = decodeSeedPolynomial(seed, W);
        vector<BigUInt> rows2 = unrankBasis(K2, R, cfg.instanceCount);
        requireTest(rows == rows2, "generated seed round-trip rows");
        for (size_t i = 0; i < rows2.size(); ++i) {
            vector<BigUInt> ids = unrankRow(cfg.components, rows2[i]);
            InstanceResult rr = makeInstanceFromIds(cfg.components, ids, i);
            for (size_t c = 0; c < 6; ++c) requireTest(rr.comp[c].rawId == inst[i].comp[c].rawId, "seed round-trip raw ids");
        }
    }
    {
        Config cfg;
        cfg.path = "<self-test-collapse>";
        cfg.instanceCount = 1;
        for (int i = 0; i < 6; ++i) cfg.components.push_back(testComponent(COMPONENT_NAMES[i], i == 0 ? "0123" : "01", FIXED, 1));
        cfg.components[0].modulus = BigUInt(2);
        map<string, string> a, b;
        for (int i = 0; i < 6; ++i) {
            a[COMPONENT_NAMES[i]] = (i == 0) ? "0" : "0";
            b[COMPONENT_NAMES[i]] = (i == 0) ? "2" : "0";
        }
        InstanceResult ia = makeInstanceFromStrings(cfg.components, a, 0);
        InstanceResult ib = makeInstanceFromStrings(cfg.components, b, 0);
        requireTest(ia.comp[0].rawId.str() == "0" && ib.comp[0].rawId.str() == "2", "alternate modulus raw ids differ");
        requireTest(ia.comp[0].residue.str() == ib.comp[0].residue.str(), "alternate modulus residues collapse");
        vector<BigUInt> ids = unrankRow(cfg.components, ib.rowOrdinal);
        requireTest(ids[0].str() == "2", "seed row addressing recovers raw id despite residue collapse");
    }
    {
        Config cfg = tinyConfig(1);
        cfg.seed.mode = "strict";
        string seedPath = "selftest_19.txt";
        string outPath = "selftest_20.txt";
        writeFile(seedPath, "0\n1\n[0, 2]\n");
        vector<SeedRecordResult> recs = buildFromSeedFile(cfg, seedPath);
        requireTest(recs.size() == 3, "multiple seed records read in order");
        writeFile(outPath, generateSeedBuildText(cfg, recs, false));
        string text = readFile(outPath);
        size_t count = 0, pos = 0;
        while ((pos = text.find("===== BASIS BLOCK", pos)) != string::npos) {
            ++count;
            pos += 5;
        }
        requireTest(count == 3, "20.txt contains same number of basis blocks");
        std::remove(seedPath.c_str());
        std::remove(outPath.c_str());
    }
    std::cout << "self-test ok\n";
}

int main(int argc, char **argv) {
    try {
        Options opt = parseOptions(argc, argv);
        if (opt.help) {
            printHelp();
            return 0;
        }
        if (opt.sample) {
            std::cout << sampleConfig();
            return 0;
        }
        if (opt.selfTest) {
            runSelfTests();
            return 0;
        }

        Config cfg = opt.interactive ? interactiveConfig(opt) : readConfigFile(opt.configPath);
        applyOptions(cfg, opt);
        if (!opt.instanceFile.empty()) loadInstanceFile(cfg, opt.instanceFile);

        if (opt.fromSeeds) {
            if (cfg.inlineInstancesPresent) {
                std::cerr << "metadata: --from-seeds active; inline instances in 17.txt are ignored for generated output sequence\n";
            }
            if (cfg.instanceCount == 0 && !opt.instancesOverride) fail("seed-build mode requires instance_count N or --instances");
            vector<SeedRecordResult> records = buildFromSeedFile(cfg, cfg.seed.seedFile);
            string text = generateSeedBuildText(cfg, records, opt.timestamp);
            writeFile(cfg.seed.basisOut, text);
            if (opt.validateOnly) std::cout << "validation_ok\n";
            else std::cout << "wrote seed-build output to " << cfg.seed.basisOut << " (" << records.size() << " basis blocks)\n";
            return 0;
        }

        if (!cfg.inlineInstancesPresent) fail("normal generation mode requires inline instances, --instance-file, or --interactive");
        vector<InstanceResult> instances = processInlineInstances(cfg);
        if (opt.validateOnly) {
            std::cout << "validation_ok\n";
            return 0;
        }
        string output = (cfg.output.format == "text") ? generateTextOutput(cfg, instances, opt.timestamp)
                                                       : generateJsonOutput(cfg, instances, opt.timestamp);
        if (!opt.writeSeedFile.empty()) writeGeneratedSeedFile(cfg, instances, opt.writeSeedFile, opt.appendSeedFile);
        if (!cfg.output.path.empty()) {
            writeFile(cfg.output.path, output);
            std::cout << "wrote " << cfg.output.format << " output to " << cfg.output.path << "\n";
        } else {
            std::cout << output;
        }
        return 0;
    } catch (const std::exception &e) {
        std::cerr << "error: " << e.what() << "\n";
        return 1;
    }
}
