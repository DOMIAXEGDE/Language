#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <ctime>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <optional>
#include <regex>
#include <sstream>
#include <stdexcept>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

namespace gpil {

constexpr std::size_t MAX_STRING_SYMBOLS = 4096;
constexpr std::size_t MAX_ALPHABET_SYMBOLS = 1024;
constexpr std::string_view DEFAULT_ALPHABET =
    " !\"#$%&'()*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ[\\]^_`abcdefghijklmnopqrstuvwxyz{|}~";

class Diagnostic final : public std::runtime_error {
public:
    Diagnostic(std::size_t line, std::size_t column, const std::string& message)
        : std::runtime_error(format(line, column, message)), line_(line), column_(column) {}

    [[nodiscard]] std::size_t line() const noexcept { return line_; }
    [[nodiscard]] std::size_t column() const noexcept { return column_; }

private:
    std::size_t line_;
    std::size_t column_;

    static std::string format(std::size_t line, std::size_t column, const std::string& message) {
        std::ostringstream output;
        output << "line " << line << ", column " << column << ": " << message;
        return output.str();
    }
};

std::vector<std::string> utf8Symbols(const std::string& value) {
    std::vector<std::string> result;
    for (std::size_t index = 0; index < value.size();) {
        const auto first = static_cast<unsigned char>(value[index]);
        std::size_t width = 0;
        std::uint32_t codePoint = 0;
        if (first <= 0x7f) {
            width = 1;
            codePoint = first;
        } else if ((first & 0xe0) == 0xc0) {
            width = 2;
            codePoint = first & 0x1f;
        } else if ((first & 0xf0) == 0xe0) {
            width = 3;
            codePoint = first & 0x0f;
        } else if ((first & 0xf8) == 0xf0) {
            width = 4;
            codePoint = first & 0x07;
        } else {
            throw std::invalid_argument("invalid UTF-8 leading byte");
        }

        if (index + width > value.size()) {
            throw std::invalid_argument("truncated UTF-8 sequence");
        }
        for (std::size_t offset = 1; offset < width; ++offset) {
            const auto continuation = static_cast<unsigned char>(value[index + offset]);
            if ((continuation & 0xc0) != 0x80) {
                throw std::invalid_argument("invalid UTF-8 continuation byte");
            }
            codePoint = (codePoint << 6) | (continuation & 0x3f);
        }

        const bool overlong = (width == 2 && codePoint < 0x80)
            || (width == 3 && codePoint < 0x800)
            || (width == 4 && codePoint < 0x10000);
        if (overlong || codePoint > 0x10ffff || (codePoint >= 0xd800 && codePoint <= 0xdfff)) {
            throw std::invalid_argument("invalid UTF-8 code point");
        }

        result.push_back(value.substr(index, width));
        index += width;
    }
    return result;
}

std::string joinSymbols(const std::vector<std::string>& symbols) {
    std::string result;
    for (const auto& symbol : symbols) {
        result += symbol;
    }
    return result;
}

namespace natural {

std::string normalize(const std::string& value) {
    if (value.empty() || !std::all_of(value.begin(), value.end(), [](unsigned char character) {
            return character >= '0' && character <= '9';
        })) {
        throw std::invalid_argument("expected a non-negative decimal integer");
    }
    const std::size_t first = value.find_first_not_of('0');
    return first == std::string::npos ? "0" : value.substr(first);
}

int compare(const std::string& leftValue, const std::string& rightValue) {
    const std::string left = normalize(leftValue);
    const std::string right = normalize(rightValue);
    if (left.size() != right.size()) return left.size() < right.size() ? -1 : 1;
    if (left == right) return 0;
    return left < right ? -1 : 1;
}

std::string add(const std::string& leftValue, const std::string& rightValue) {
    const std::string left = normalize(leftValue);
    const std::string right = normalize(rightValue);
    std::string result;
    int carry = 0;
    std::size_t leftIndex = left.size();
    std::size_t rightIndex = right.size();
    while (leftIndex > 0 || rightIndex > 0 || carry > 0) {
        const int leftDigit = leftIndex > 0 ? left[--leftIndex] - '0' : 0;
        const int rightDigit = rightIndex > 0 ? right[--rightIndex] - '0' : 0;
        const int sum = leftDigit + rightDigit + carry;
        result.push_back(static_cast<char>('0' + (sum % 10)));
        carry = sum / 10;
    }
    std::reverse(result.begin(), result.end());
    return result;
}

std::string subtract(const std::string& leftValue, const std::string& rightValue) {
    const std::string left = normalize(leftValue);
    const std::string right = normalize(rightValue);
    if (compare(left, right) < 0) throw std::invalid_argument("natural subtraction would be negative");
    std::string result;
    int borrow = 0;
    std::size_t rightIndex = right.size();
    for (std::size_t leftIndex = left.size(); leftIndex > 0;) {
        int digit = left[--leftIndex] - '0' - borrow;
        const int subtrahend = rightIndex > 0 ? right[--rightIndex] - '0' : 0;
        if (digit < subtrahend) {
            digit += 10;
            borrow = 1;
        } else {
            borrow = 0;
        }
        result.push_back(static_cast<char>('0' + digit - subtrahend));
    }
    std::reverse(result.begin(), result.end());
    return normalize(result);
}

std::string multiplySmall(const std::string& value, std::size_t factor) {
    const std::string number = normalize(value);
    if (number == "0" || factor == 0) return "0";
    std::string result;
    std::uint64_t carry = 0;
    for (std::size_t index = number.size(); index > 0;) {
        const std::uint64_t product = static_cast<std::uint64_t>(number[--index] - '0') * factor + carry;
        result.push_back(static_cast<char>('0' + product % 10));
        carry = product / 10;
    }
    while (carry > 0) {
        result.push_back(static_cast<char>('0' + carry % 10));
        carry /= 10;
    }
    std::reverse(result.begin(), result.end());
    return result;
}

std::string multiply(const std::string& leftValue, const std::string& rightValue) {
    const std::string left = normalize(leftValue);
    const std::string right = normalize(rightValue);
    if (left == "0" || right == "0") return "0";
    std::vector<int> digits(left.size() + right.size(), 0);
    for (std::size_t leftIndex = left.size(); leftIndex > 0;) {
        --leftIndex;
        for (std::size_t rightIndex = right.size(); rightIndex > 0;) {
            --rightIndex;
            const std::size_t position = leftIndex + rightIndex + 1;
            const int product = (left[leftIndex] - '0') * (right[rightIndex] - '0') + digits[position];
            digits[position] = product % 10;
            digits[position - 1] += product / 10;
        }
    }
    std::string result;
    std::size_t first = 0;
    while (first + 1 < digits.size() && digits[first] == 0) ++first;
    for (; first < digits.size(); ++first) result.push_back(static_cast<char>('0' + digits[first]));
    return normalize(result);
}

std::pair<std::string, std::size_t> divideSmall(const std::string& value, std::size_t divisor) {
    const std::string number = normalize(value);
    if (divisor == 0) throw std::invalid_argument("division by zero");
    std::string quotient;
    std::size_t remainder = 0;
    for (const char digit : number) {
        const std::uint64_t partial = static_cast<std::uint64_t>(remainder) * 10 + (digit - '0');
        quotient.push_back(static_cast<char>('0' + partial / divisor));
        remainder = static_cast<std::size_t>(partial % divisor);
    }
    return {normalize(quotient), remainder};
}

std::pair<std::string, std::string> divide(const std::string& dividendValue, const std::string& divisorValue) {
    const std::string dividend = normalize(dividendValue);
    const std::string divisor = normalize(divisorValue);
    if (divisor == "0") throw std::invalid_argument("division by zero");
    if (compare(dividend, divisor) < 0) return {"0", dividend};

    std::string quotient;
    std::string remainder = "0";
    for (const char digit : dividend) {
        remainder = normalize(remainder == "0" ? std::string(1, digit) : remainder + digit);
        int low = 0;
        int high = 9;
        int selected = 0;
        while (low <= high) {
            const int middle = (low + high) / 2;
            if (compare(multiplySmall(divisor, static_cast<std::size_t>(middle)), remainder) <= 0) {
                selected = middle;
                low = middle + 1;
            } else {
                high = middle - 1;
            }
        }
        quotient.push_back(static_cast<char>('0' + selected));
        if (selected > 0) remainder = subtract(remainder, multiplySmall(divisor, selected));
    }
    return {normalize(quotient), normalize(remainder)};
}

} // namespace natural

std::string parseNatural(const std::string& value, std::string_view context = "value") {
    try {
        return natural::normalize(value);
    } catch (const std::invalid_argument&) {
        throw std::invalid_argument(std::string(context) + " must be a non-negative decimal integer");
    }
}

struct BigInteger {
    bool negative = false;
    std::string magnitude = "0";
};

BigInteger parseInteger(const std::string& value, std::string_view context = "value") {
    if (value.empty()) throw std::invalid_argument(std::string(context) + " must be a decimal integer");
    const bool negative = value.front() == '-';
    const std::string digits = negative ? value.substr(1) : value;
    const std::string magnitude = parseNatural(digits, context);
    return {negative && magnitude != "0", magnitude};
}

std::string decimal(const BigInteger& value) {
    return value.negative && value.magnitude != "0" ? "-" + value.magnitude : value.magnitude;
}

BigInteger negate(BigInteger value) {
    if (value.magnitude != "0") value.negative = !value.negative;
    return value;
}

BigInteger addInteger(const BigInteger& left, const BigInteger& right) {
    if (left.negative == right.negative) {
        return {left.negative, natural::add(left.magnitude, right.magnitude)};
    }
    const int comparison = natural::compare(left.magnitude, right.magnitude);
    if (comparison == 0) return {};
    if (comparison > 0) return {left.negative, natural::subtract(left.magnitude, right.magnitude)};
    return {right.negative, natural::subtract(right.magnitude, left.magnitude)};
}

BigInteger multiplyInteger(const BigInteger& left, const BigInteger& right) {
    const std::string magnitude = natural::multiply(left.magnitude, right.magnitude);
    return {magnitude != "0" && left.negative != right.negative, magnitude};
}

std::pair<BigInteger, BigInteger> divideInteger(const BigInteger& dividend, const BigInteger& divisor) {
    if (divisor.magnitude == "0") throw std::invalid_argument("division by zero");
    auto [quotient, remainder] = natural::divide(dividend.magnitude, divisor.magnitude);
    return {
        {quotient != "0" && dividend.negative != divisor.negative, quotient},
        {remainder != "0" && dividend.negative, remainder},
    };
}

class Shortlex final {
public:
    explicit Shortlex(std::string alphabet) : alphabet_(std::move(alphabet)), symbols_(utf8Symbols(alphabet_)) {
        if (symbols_.size() < 2) {
            throw std::invalid_argument("alphabet must contain at least two symbols");
        }
        if (symbols_.size() > MAX_ALPHABET_SYMBOLS) {
            throw std::invalid_argument("alphabet exceeds 1024 symbols");
        }
        for (std::size_t left = 0; left < symbols_.size(); ++left) {
            for (std::size_t right = left + 1; right < symbols_.size(); ++right) {
                if (symbols_[left] == symbols_[right]) {
                    throw std::invalid_argument("alphabet contains a duplicate symbol");
                }
            }
        }
    }

    [[nodiscard]] const std::string& alphabet() const noexcept { return alphabet_; }
    [[nodiscard]] std::size_t alphabetSize() const noexcept { return symbols_.size(); }

    [[nodiscard]] std::string encode(const std::string& input) const {
        const auto inputSymbols = utf8Symbols(input);
        if (inputSymbols.size() > MAX_STRING_SYMBOLS) {
            throw std::invalid_argument("string-input exceeds 4096 symbols");
        }
        if (inputSymbols.empty()) {
            return "0";
        }

        std::string shorterStringCount = "0";
        std::string stringsAtLength = "1";
        for (std::size_t size = 1; size < inputSymbols.size(); ++size) {
            stringsAtLength = natural::multiplySmall(stringsAtLength, symbols_.size());
            shorterStringCount = natural::add(shorterStringCount, stringsAtLength);
        }

        std::string rank = "0";
        for (const auto& symbol : inputSymbols) {
            const auto found = std::find(symbols_.begin(), symbols_.end(), symbol);
            if (found == symbols_.end()) {
                throw std::invalid_argument("string-input contains a symbol outside its event alphabet");
            }
            rank = natural::multiplySmall(rank, symbols_.size());
            rank = natural::add(rank, std::to_string(std::distance(symbols_.begin(), found)));
        }
        return natural::add(natural::add(shorterStringCount, rank), "1");
    }

    [[nodiscard]] std::string decode(const std::string& idValue) const {
        const std::string id = parseNatural(idValue, "sequential-string ID");
        if (id == "0") {
            return {};
        }

        std::string remaining = id;
        std::string bucketSize = std::to_string(symbols_.size());
        std::size_t length = 1;
        while (natural::compare(remaining, bucketSize) > 0) {
            remaining = natural::subtract(remaining, bucketSize);
            bucketSize = natural::multiplySmall(bucketSize, symbols_.size());
            if (++length > MAX_STRING_SYMBOLS) {
                throw std::invalid_argument("sequential-string ID exceeds the supported context size");
            }
        }

        std::string offset = natural::subtract(remaining, "1");
        std::vector<std::string> decoded(length, symbols_.front());
        for (std::size_t position = length; position > 0; --position) {
            auto [quotient, remainder] = natural::divideSmall(offset, symbols_.size());
            offset = quotient;
            decoded[position - 1] = symbols_[remainder];
        }
        return joinSymbols(decoded);
    }

private:
    std::string alphabet_;
    std::vector<std::string> symbols_;
};

enum class TokenKind {
    identifier,
    stringLiteral,
    number,
    reference,
    colon,
    leftParen,
    rightParen,
    comma,
    semicolon,
    end,
};

struct Token {
    TokenKind kind;
    std::string text;
    std::size_t column;
};

class Lexer final {
public:
    Lexer(std::string_view source, std::size_t line) : source_(source), line_(line) {}

    Token next() {
        skipWhitespace();
        if (position_ >= source_.size()) {
            return {TokenKind::end, {}, position_ + 1};
        }
        const std::size_t column = position_ + 1;
        const char character = source_[position_];
        switch (character) {
            case ':': ++position_; return {TokenKind::colon, ":", column};
            case '(': ++position_; return {TokenKind::leftParen, "(", column};
            case ')': ++position_; return {TokenKind::rightParen, ")", column};
            case ',': ++position_; return {TokenKind::comma, ",", column};
            case ';': ++position_; return {TokenKind::semicolon, ";", column};
            case '"': return stringToken();
            case '$': return referenceToken();
            default: break;
        }

        if (isIdentifierStart(character)) {
            return identifierToken();
        }
        if (character == '-' || (character >= '0' && character <= '9')) {
            return numberToken();
        }
        throw Diagnostic(line_, column, std::string("unexpected character '") + character + "'");
    }

private:
    std::string_view source_;
    std::size_t line_;
    std::size_t position_ = 0;

    void skipWhitespace() {
        while (position_ < source_.size() && (source_[position_] == ' ' || source_[position_] == '\t')) {
            ++position_;
        }
    }

    static bool isIdentifierStart(char character) {
        return (character >= 'a' && character <= 'z') || (character >= 'A' && character <= 'Z') || character == '_';
    }

    static bool isIdentifierPart(char character) {
        return isIdentifierStart(character) || (character >= '0' && character <= '9');
    }

    Token identifierToken() {
        const std::size_t start = position_++;
        while (position_ < source_.size() && isIdentifierPart(source_[position_])) {
            ++position_;
        }
        return {TokenKind::identifier, std::string(source_.substr(start, position_ - start)), start + 1};
    }

    Token numberToken() {
        const std::size_t start = position_;
        if (source_[position_] == '-') {
            ++position_;
        }
        const std::size_t digits = position_;
        while (position_ < source_.size() && source_[position_] >= '0' && source_[position_] <= '9') {
            ++position_;
        }
        if (digits == position_) {
            throw Diagnostic(line_, start + 1, "minus sign must be followed by digits");
        }
        return {TokenKind::number, std::string(source_.substr(start, position_ - start)), start + 1};
    }

    Token referenceToken() {
        const std::size_t start = position_++;
        const std::size_t digits = position_;
        while (position_ < source_.size() && source_[position_] >= '0' && source_[position_] <= '9') {
            ++position_;
        }
        if (digits == position_) {
            throw Diagnostic(line_, start + 1, "event reference must be '$' followed by a 1-based line number");
        }
        return {TokenKind::reference, std::string(source_.substr(digits, position_ - digits)), start + 1};
    }

    Token stringToken() {
        const std::size_t start = position_++;
        std::string result;
        while (position_ < source_.size()) {
            const char character = source_[position_++];
            if (character == '"') {
                try {
                    (void) utf8Symbols(result);
                } catch (const std::invalid_argument& error) {
                    throw Diagnostic(line_, start + 1, std::string("string literal is not valid UTF-8: ") + error.what());
                }
                return {TokenKind::stringLiteral, result, start + 1};
            }
            if (character != '\\') {
                result += character;
                continue;
            }
            if (position_ >= source_.size()) {
                throw Diagnostic(line_, start + 1, "unterminated string escape");
            }
            const char escaped = source_[position_++];
            switch (escaped) {
                case '"': result += '"'; break;
                case '\\': result += '\\'; break;
                case 'n': result += '\n'; break;
                case 'r': result += '\r'; break;
                case 't': result += '\t'; break;
                default:
                    throw Diagnostic(line_, position_, std::string("unsupported escape '\\") + escaped + "'");
            }
        }
        throw Diagnostic(line_, start + 1, "unterminated string literal");
    }
};

struct Expression {
    enum class Kind { literal, reference, call } kind = Kind::literal;
    std::string text;
    std::size_t reference = 0;
    std::vector<Expression> arguments;
};

struct Statement {
    std::size_t line = 0;
    std::string label;
    Expression expression;
    std::string alphabet = std::string(DEFAULT_ALPHABET);
    std::string source;
};

class Parser final {
public:
    Parser(std::string source, std::size_t line)
        : source_(std::move(source)), line_(line), lexer_(source_, line_) {
        advance();
    }

    Statement parse() {
        const Token event = require(TokenKind::identifier, "expected 'event'");
        if (event.text != "event") {
            throw Diagnostic(line_, event.column, "each line must begin with 'event'");
        }
        const std::string label = require(TokenKind::stringLiteral, "expected an event label string").text;
        require(TokenKind::colon, "expected ':' after event label");
        Expression expression = parseExpression();

        std::string alphabet(DEFAULT_ALPHABET);
        if (current_.kind == TokenKind::identifier && current_.text == "alphabet") {
            advance();
            alphabet = require(TokenKind::stringLiteral, "expected alphabet string").text;
        }
        if (current_.kind == TokenKind::semicolon) {
            advance();
        }
        require(TokenKind::end, "unexpected text after event");
        return {line_, label, std::move(expression), alphabet, source_};
    }

private:
    std::string source_;
    std::size_t line_;
    Lexer lexer_;
    Token current_{TokenKind::end, {}, 1};

    void advance() { current_ = lexer_.next(); }

    Token require(TokenKind kind, const std::string& message) {
        if (current_.kind != kind) {
            throw Diagnostic(line_, current_.column, message);
        }
        Token result = current_;
        advance();
        return result;
    }

    Expression parseExpression() {
        if (current_.kind == TokenKind::stringLiteral || current_.kind == TokenKind::number) {
            Expression result;
            result.kind = Expression::Kind::literal;
            result.text = current_.text;
            advance();
            return result;
        }
        if (current_.kind == TokenKind::reference) {
            Expression result;
            result.kind = Expression::Kind::reference;
            try {
                result.reference = static_cast<std::size_t>(std::stoull(current_.text));
            } catch (const std::exception&) {
                throw Diagnostic(line_, current_.column, "event reference is too large");
            }
            advance();
            return result;
        }
        if (current_.kind != TokenKind::identifier) {
            throw Diagnostic(line_, current_.column, "expected a literal, event reference, or built-in call");
        }

        Expression result;
        result.kind = Expression::Kind::call;
        result.text = current_.text;
        advance();
        require(TokenKind::leftParen, "expected '(' after built-in name");
        if (current_.kind != TokenKind::rightParen) {
            while (true) {
                result.arguments.push_back(parseExpression());
                if (current_.kind != TokenKind::comma) {
                    break;
                }
                advance();
            }
        }
        require(TokenKind::rightParen, "expected ')' after built-in arguments");
        return result;
    }
};

struct EvaluationContext {
    const std::vector<std::string>& previousValues;
};

bool truth(const std::string& value) {
    if (value == "true") return true;
    if (value == "false") return false;
    throw std::invalid_argument("Boolean argument must be 'true' or 'false'");
}

void requireArity(std::string_view name, const std::vector<std::string>& arguments, std::size_t count) {
    if (arguments.size() != count) {
        std::ostringstream message;
        message << name << " expects " << count << " argument" << (count == 1 ? "" : "s")
                << "; received " << arguments.size();
        throw std::invalid_argument(message.str());
    }
}

std::string containerize(const std::string& payload) {
    return "GPDB1:" + std::to_string(payload.size()) + ":" + payload;
}

std::string decontainerize(const std::string& container) {
    constexpr std::string_view prefix = "GPDB1:";
    if (!container.starts_with(prefix)) {
        throw std::invalid_argument("container must begin with 'GPDB1:'");
    }
    const std::size_t separator = container.find(':', prefix.size());
    if (separator == std::string::npos) {
        throw std::invalid_argument("container length separator is missing");
    }
    const std::string lengthText = container.substr(prefix.size(), separator - prefix.size());
    const std::string length = parseNatural(lengthText, "container byte length");
    if (natural::compare(length, std::to_string(std::numeric_limits<std::size_t>::max())) > 0) {
        throw std::invalid_argument("container byte length exceeds native address space");
    }
    const std::string payload = container.substr(separator + 1);
    if (payload.size() != static_cast<std::size_t>(std::stoull(length))) {
        throw std::invalid_argument("container byte length does not match its payload");
    }
    (void) utf8Symbols(payload);
    return payload;
}

std::string replaceAll(std::string value, const std::string& search, const std::string& replacement) {
    if (search.empty()) {
        throw std::invalid_argument("replace search text cannot be empty");
    }
    std::size_t position = 0;
    while ((position = value.find(search, position)) != std::string::npos) {
        value.replace(position, search.size(), replacement);
        position += replacement.size();
    }
    return value;
}

std::string reverseUtf8(const std::string& value) {
    auto symbols = utf8Symbols(value);
    std::reverse(symbols.begin(), symbols.end());
    return joinSymbols(symbols);
}

std::string asciiUpper(std::string value) {
    std::transform(value.begin(), value.end(), value.begin(), [](unsigned char character) {
        return character >= 'a' && character <= 'z' ? static_cast<char>(character - 32) : static_cast<char>(character);
    });
    return value;
}

std::string asciiLower(std::string value) {
    std::transform(value.begin(), value.end(), value.begin(), [](unsigned char character) {
        return character >= 'A' && character <= 'Z' ? static_cast<char>(character + 32) : static_cast<char>(character);
    });
    return value;
}

std::string evaluateCall(const std::string& name, const std::vector<std::string>& args) {
    if (name == "literal" || name == "identity") {
        requireArity(name, args, 1);
        return args[0];
    }
    if (name == "add") {
        requireArity(name, args, 2);
        return decimal(addInteger(parseInteger(args[0], "left addend"), parseInteger(args[1], "right addend")));
    }
    if (name == "subtract") {
        requireArity(name, args, 2);
        return decimal(addInteger(parseInteger(args[0], "minuend"), negate(parseInteger(args[1], "subtrahend"))));
    }
    if (name == "multiply") {
        requireArity(name, args, 2);
        return decimal(multiplyInteger(parseInteger(args[0], "left factor"), parseInteger(args[1], "right factor")));
    }
    if (name == "divide" || name == "modulo") {
        requireArity(name, args, 2);
        const BigInteger dividend = parseInteger(args[0], "dividend");
        const BigInteger divisor = parseInteger(args[1], "divisor");
        if (divisor.magnitude == "0") throw std::invalid_argument(name + " divisor cannot be zero");
        auto [quotient, remainder] = divideInteger(dividend, divisor);
        return decimal(name == "divide" ? quotient : remainder);
    }
    if (name == "apply_directional_polarity") {
        requireArity(name, args, 2);
        BigInteger value = parseInteger(args[0], "polarity value");
        BigInteger magnitude{false, value.magnitude};
        if (args[1] == "positive" || args[1] == "forward") return decimal(magnitude);
        if (args[1] == "negative" || args[1] == "backward") return decimal(negate(magnitude));
        if (args[1] == "invert") return decimal(negate(value));
        throw std::invalid_argument("polarity direction must be positive, negative, forward, backward, or invert");
    }
    if (name == "containerize") {
        requireArity(name, args, 1);
        return containerize(args[0]);
    }
    if (name == "decontainerize") {
        requireArity(name, args, 1);
        return decontainerize(args[0]);
    }
    if (name == "transform_container") {
        if (args.size() < 2 || args.size() > 4) {
            throw std::invalid_argument("transform_container expects 2 to 4 arguments");
        }
        std::string payload = decontainerize(args[0]);
        if (args[1] == "reverse") payload = reverseUtf8(payload);
        else if (args[1] == "uppercase") payload = asciiUpper(payload);
        else if (args[1] == "lowercase") payload = asciiLower(payload);
        else if (args[1] == "append" && args.size() == 3) payload += args[2];
        else if (args[1] == "prepend" && args.size() == 3) payload = args[2] + payload;
        else if (args[1] == "replace" && args.size() == 4) payload = replaceAll(payload, args[2], args[3]);
        else throw std::invalid_argument("invalid transform_container operation or operand count");
        return containerize(payload);
    }
    if (name == "concat") {
        if (args.empty()) throw std::invalid_argument("concat expects at least one argument");
        std::string result;
        for (const auto& argument : args) result += argument;
        return result;
    }
    if (name == "symbol_length") {
        requireArity(name, args, 1);
        return std::to_string(utf8Symbols(args[0]).size());
    }
    if (name == "reverse") {
        requireArity(name, args, 1);
        return reverseUtf8(args[0]);
    }
    if (name == "replace") {
        requireArity(name, args, 3);
        return replaceAll(args[0], args[1], args[2]);
    }
    if (name == "equal") {
        requireArity(name, args, 2);
        return args[0] == args[1] ? "true" : "false";
    }
    if (name == "not") {
        requireArity(name, args, 1);
        return truth(args[0]) ? "false" : "true";
    }
    if (name == "and" || name == "or") {
        requireArity(name, args, 2);
        const bool left = truth(args[0]);
        const bool right = truth(args[1]);
        return (name == "and" ? left && right : left || right) ? "true" : "false";
    }
    if (name == "select") {
        requireArity(name, args, 3);
        return truth(args[0]) ? args[1] : args[2];
    }
    if (name == "assert_equal") {
        requireArity(name, args, 2);
        if (args[0] != args[1]) throw std::invalid_argument("assert_equal failed");
        return args[0];
    }
    if (name == "semantic_triple") {
        requireArity(name, args, 3);
        return args[0] + " <" + args[1] + "> " + args[2];
    }
    if (name == "sequential_encode") {
        requireArity(name, args, 2);
        return Shortlex(args[1]).encode(args[0]);
    }
    if (name == "sequential_decode") {
        requireArity(name, args, 2);
        return Shortlex(args[1]).decode(parseNatural(args[0], "sequential-string ID"));
    }
    if (name == "sequential_verify") {
        requireArity(name, args, 2);
        const Shortlex sequence(args[1]);
        return sequence.decode(sequence.encode(args[0])) == args[0] ? "true" : "false";
    }
    if (name == "map_coordinate") {
        requireArity(name, args, 2);
        const std::string indexValue = parseNatural(args[0], "map index");
        const std::string countValue = parseNatural(args[1], "map event count");
        if (countValue == "0" || natural::compare(indexValue, countValue) >= 0) {
            throw std::invalid_argument("map index must be less than a positive event count");
        }
        if (natural::compare(countValue, std::to_string(std::numeric_limits<std::uint64_t>::max())) > 0) {
            throw std::invalid_argument("map event count exceeds the addressable compiler context");
        }
        const auto count = static_cast<std::uint64_t>(std::stoull(countValue));
        const auto index = static_cast<std::uint64_t>(std::stoull(indexValue));
        std::uint64_t side = static_cast<std::uint64_t>(std::ceil(std::sqrt(static_cast<long double>(count))));
        while (side > 1 && (side - 1) * (side - 1) >= count) --side;
        while (side * side < count) ++side;
        return std::to_string(index / side) + "," + std::to_string(index % side);
    }
    throw std::invalid_argument("unknown built-in '" + name + "'");
}

std::string evaluate(const Expression& expression, const EvaluationContext& context) {
    if (expression.kind == Expression::Kind::literal) {
        return expression.text;
    }
    if (expression.kind == Expression::Kind::reference) {
        if (expression.reference == 0 || expression.reference > context.previousValues.size()) {
            throw std::invalid_argument("event reference must name an earlier 1-based event ordinal");
        }
        return context.previousValues[expression.reference - 1];
    }
    std::vector<std::string> arguments;
    arguments.reserve(expression.arguments.size());
    for (const auto& argument : expression.arguments) {
        arguments.push_back(evaluate(argument, context));
    }
    return evaluateCall(expression.text, arguments);
}

std::string jsonEscape(const std::string& value) {
    std::ostringstream output;
    for (const unsigned char character : value) {
        switch (character) {
            case '"': output << "\\\""; break;
            case '\\': output << "\\\\"; break;
            case '\b': output << "\\b"; break;
            case '\f': output << "\\f"; break;
            case '\n': output << "\\n"; break;
            case '\r': output << "\\r"; break;
            case '\t': output << "\\t"; break;
            default:
                if (character < 0x20) {
                    output << "\\u" << std::hex << std::setw(4) << std::setfill('0')
                           << static_cast<int>(character) << std::dec << std::setfill(' ');
                } else {
                    output << static_cast<char>(character);
                }
        }
    }
    return output.str();
}

std::string isoTimestamp() {
    const auto now = std::chrono::system_clock::now();
    const auto milliseconds = std::chrono::duration_cast<std::chrono::milliseconds>(now.time_since_epoch()) % 1000;
    const std::time_t time = std::chrono::system_clock::to_time_t(now);
    std::tm utc{};
#ifdef _WIN32
    gmtime_s(&utc, &time);
#else
    gmtime_r(&time, &utc);
#endif
    std::ostringstream output;
    output << std::put_time(&utc, "%Y-%m-%dT%H:%M:%S") << '.'
           << std::setw(3) << std::setfill('0') << milliseconds.count() << 'Z';
    return output.str();
}

std::uint64_t fnv1a(const std::string& value) {
    std::uint64_t hash = 14695981039346656037ull;
    for (const unsigned char character : value) {
        hash ^= character;
        hash *= 1099511628211ull;
    }
    return hash;
}

std::string eventId(const Statement& statement) {
    std::ostringstream output;
    output << "gpil_" << std::setw(4) << std::setfill('0') << statement.line << '_'
           << std::hex << std::setw(16) << std::setfill('0')
           << fnv1a(statement.source + "\n" + statement.label);
    return output.str();
}

struct Event {
    Statement statement;
    std::string timestamp;
    std::string value;
    std::string id;
    std::string sequentialId;
    std::string backwardValue;
    std::size_t alphabetSymbols = 0;
    std::size_t valueSymbols = 0;
    bool nativeInteger = false;
};

std::vector<Statement> parseProgram(std::istream& input) {
    std::vector<Statement> statements;
    std::string line;
    std::size_t physicalLine = 0;
    while (std::getline(input, line)) {
        ++physicalLine;
        if (!line.empty() && line.back() == '\r') line.pop_back();
        if (line.empty() || std::all_of(line.begin(), line.end(), [](unsigned char character) {
                return character == ' ' || character == '\t';
            })) {
            continue;
        }
        statements.push_back(Parser(line, physicalLine).parse());
    }
    if (statements.empty()) {
        throw std::invalid_argument("program contains no event lines");
    }
    return statements;
}

std::vector<Event> compile(const std::vector<Statement>& statements) {
    std::vector<Event> events;
    std::vector<std::string> values;
    events.reserve(statements.size());
    values.reserve(statements.size());
    const std::string timestamp = isoTimestamp();

    for (const auto& statement : statements) {
        try {
            const std::string value = evaluate(statement.expression, {values});
            const Shortlex sequence(statement.alphabet);
            const std::string encoded = sequence.encode(value);
            const std::string backward = sequence.decode(encoded);
            if (backward != value) {
                throw std::runtime_error("internal round-trip proof failed");
            }
            const std::string id = encoded;
            events.push_back({
                statement,
                timestamp,
                value,
                eventId(statement),
                id,
                backward,
                sequence.alphabetSize(),
                utf8Symbols(value).size(),
                natural::compare(encoded, std::to_string(std::numeric_limits<std::int64_t>::max())) <= 0,
            });
            values.push_back(value);
        } catch (const Diagnostic&) {
            throw;
        } catch (const std::exception& error) {
            throw Diagnostic(statement.line, 1, error.what());
        }
    }
    return events;
}

std::string expressionName(const Expression& expression) {
    if (expression.kind == Expression::Kind::call) return expression.text;
    if (expression.kind == Expression::Kind::reference) return "reference";
    return "literal";
}

void writeDatabase(std::ostream& output, const std::vector<Event>& events, const std::string& sourceFile) {
    const std::size_t count = events.size();
    const std::size_t side = std::max<std::size_t>(1, static_cast<std::size_t>(std::ceil(std::sqrt(static_cast<long double>(std::max<std::size_t>(1, count))))));
    const std::size_t total = side * side;
    const std::string updatedAt = events.empty() ? isoTimestamp() : events.back().timestamp;

    output << "{\n"
           << "  \"schema\": \"memory-event-node/2.0\",\n"
           << "  \"updated-at\": \"" << jsonEscape(updatedAt) << "\",\n"
           << "  \"compiler\": {\n"
           << "    \"name\": \"gpilc\",\n"
           << "    \"version\": \"1.0.0\",\n"
           << "    \"language\": \"GPIL/1.0\",\n"
           << "    \"source\": \"" << jsonEscape(sourceFile) << "\",\n"
           << "    \"line-contract\": \"one nonblank physical source line equals one event\"\n"
           << "  },\n"
           << "  \"instruction-set\": {\n"
           << "    \"array-1-construction\": [\"add\", \"apply_directional_polarity\", \"containerize\", \"decontainerize\"],\n"
           << "    \"array-2-container-transformation\": [\"transform_container\"],\n"
           << "    \"array-3-arithmetic\": [\"subtract\", \"multiply\", \"divide\", \"modulo\"],\n"
           << "    \"array-4-text\": [\"literal\", \"identity\", \"concat\", \"symbol_length\", \"reverse\", \"replace\"],\n"
           << "    \"array-5-logic\": [\"equal\", \"not\", \"and\", \"or\", \"select\", \"assert_equal\"],\n"
           << "    \"array-6-semantics\": [\"semantic_triple\"],\n"
           << "    \"array-7-sequential-ID\": [\"sequential_encode\", \"sequential_decode\", \"sequential_verify\"],\n"
           << "    \"array-8-memory-map\": [\"reference\", \"map_coordinate\", \"automatic_event_capture\", \"automatic_square_map\"]\n"
           << "  },\n"
           << "  \"events\": [\n";

    for (std::size_t index = 0; index < events.size(); ++index) {
        const Event& event = events[index];
        output << "    {\n"
               << "      \"time-stamp\": \"" << jsonEscape(event.timestamp) << "\",\n"
               << "      \"label\": \"" << jsonEscape(event.statement.label) << "\",\n"
               << "      \"value\": \"" << jsonEscape(event.value) << "\",\n"
               << "      \"ID\": \"" << jsonEscape(event.id) << "\",\n"
               << "      \"sequential-string ID\": \"" << event.sequentialId << "\",\n"
               << "      \"backward-computed value\": \"" << jsonEscape(event.backwardValue) << "\",\n"
               << "      \"backward-computation\": {\n"
               << "        \"algorithm\": \"shortlex-unrank/1.0\",\n"
               << "        \"matches-value\": true\n"
               << "      },\n"
               << "      \"alphabet\": \"" << jsonEscape(event.statement.alphabet) << "\",\n"
               << "      \"metrics\": {\n"
               << "        \"alphabet-symbols\": " << event.alphabetSymbols << ",\n"
               << "        \"value-symbols\": " << event.valueSymbols << ",\n"
               << "        \"sequential-ID-digits\": " << event.sequentialId.size() << ",\n"
               << "        \"native-integer\": " << (event.nativeInteger ? "true" : "false") << "\n"
               << "      },\n"
               << "      \"instruction\": {\n"
               << "        \"language\": \"GPIL/1.0\",\n"
               << "        \"source-line\": " << event.statement.line << ",\n"
               << "        \"operation\": \"" << jsonEscape(expressionName(event.statement.expression)) << "\",\n"
               << "        \"source\": \"" << jsonEscape(event.statement.source) << "\"\n"
               << "      }\n"
               << "    }" << (index + 1 == events.size() ? "\n" : ",\n");
    }

    output << "  ],\n"
           << "  \"map\": {\n"
           << "    \"dimensions\": {\"rows\": " << side << ", \"columns\": " << side << "},\n"
           << "    \"cells-total\": " << total << ",\n"
           << "    \"cells-occupied\": " << count << ",\n"
           << "    \"cells-vacant\": " << (total - count) << ",\n"
           << "    \"cells\": [\n";
    for (std::size_t row = 0; row < side; ++row) {
        output << "      [";
        for (std::size_t column = 0; column < side; ++column) {
            const std::size_t index = row * side + column;
            if (index < events.size()) output << '"' << jsonEscape(events[index].id) << '"';
            else output << "null";
            if (column + 1 != side) output << ", ";
        }
        output << ']' << (row + 1 == side ? "\n" : ",\n");
    }
    output << "    ]\n  }\n}\n";
}

int selfTest() {
    const Shortlex binary("ab");
    const std::vector<std::pair<std::string, std::string>> cases = {
        {"", "0"}, {"a", "1"}, {"b", "2"}, {"aa", "3"}, {"ab", "4"}, {"ba", "5"}, {"bb", "6"},
    };
    for (const auto& [value, expected] : cases) {
        const std::string id = binary.encode(value);
        if (id != expected || binary.decode(id) != value) {
            std::cerr << "shortlex self-test failed for '" << value << "'\n";
            return 1;
        }
    }
    const Shortlex unicode("\xCE\xB1\xCE\xB2\xF0\x9F\x99\x82 ");
    const std::string unicodeValue = "\xF0\x9F\x99\x82 \xCE\xB1\xCE\xB2";
    if (unicode.decode(unicode.encode(unicodeValue)) != unicodeValue) {
        std::cerr << "Unicode shortlex self-test failed\n";
        return 1;
    }
    if (evaluateCall("add", {"99999999999999999999", "1"}) != "100000000000000000000"
        || evaluateCall("multiply", {"123456789", "987654321"}) != "121932631112635269"
        || evaluateCall("divide", {"-121932631112635269", "987654321"}) != "-123456789"
        || evaluateCall("modulo", {"-100", "9"}) != "-1") {
        std::cerr << "arbitrary-precision arithmetic self-test failed\n";
        return 1;
    }
    std::istringstream program(
        "event \"sum\" : add(40, 2)\n"
        "event \"box\" : containerize(\"space\")\n"
        "event \"unbox\" : decontainerize($2)\n"
        "event \"proof\" : assert_equal($3, \"space\")\n"
    );
    const auto events = compile(parseProgram(program));
    if (events.size() != 4 || events[0].value != "42" || events[3].value != "space") {
        std::cerr << "compiler self-test failed\n";
        return 1;
    }
    std::cout << "gpilc self-test passed\n";
    return 0;
}

} // namespace gpil

int main(int argc, char** argv) {
    using namespace gpil;
    try {
        if (argc == 2 && std::string_view(argv[1]) == "--self-test") {
            return selfTest();
        }
        if (argc < 2) {
            std::cerr << "Usage: gpilc <program.gpil> [--output <events.json>]\n"
                      << "       gpilc --self-test\n";
            return 64;
        }

        const std::string sourcePath = argv[1];
        std::optional<std::string> outputPath;
        for (int index = 2; index < argc; ++index) {
            const std::string argument = argv[index];
            if (argument == "--output" && index + 1 < argc) {
                outputPath = argv[++index];
            } else {
                throw std::invalid_argument("unknown command-line argument '" + argument + "'");
            }
        }

        std::ifstream source(sourcePath, std::ios::binary);
        if (!source) throw std::runtime_error("cannot open source file '" + sourcePath + "'");
        const auto statements = parseProgram(source);
        const auto events = compile(statements);

        if (outputPath) {
            std::ofstream output(*outputPath, std::ios::binary | std::ios::trunc);
            if (!output) throw std::runtime_error("cannot open output file '" + *outputPath + "'");
            writeDatabase(output, events, sourcePath);
            if (!output) throw std::runtime_error("failed while writing output file '" + *outputPath + "'");
        } else {
            writeDatabase(std::cout, events, sourcePath);
        }
        std::cerr << "gpilc: compiled " << events.size() << " event line"
                  << (events.size() == 1 ? "" : "s") << " with exact reverse proofs\n";
        return 0;
    } catch (const Diagnostic& error) {
        std::cerr << "gpilc: error: " << error.what() << '\n';
        return 2;
    } catch (const std::exception& error) {
        std::cerr << "gpilc: error: " << error.what() << '\n';
        return 1;
    }
}
