#include <stdio.h>
#include <stdint.h>
#include <stdbool.h>
#include <limits.h>
#define x0 10
static const char x1[] = {
    '0', '1', '2', '3', '4', '5', '6', '7', '8', '9'
};
static const uint64_t x2 = sizeof(x1) / sizeof(x1[0]);
typedef struct {
    void* x4;
    bool (*x5)(void* x4, const char* x6, uint64_t x7);
    bool (*x8)(void* x4, char x9);
} x3;
static bool x10(uint64_t x11, uint64_t x12, uint64_t* x13) {
    *x13 = 1;
    for (uint64_t x14 = 0; x14 < x12; ++x14) {
        if (*x13 > UINT64_MAX / x11) {
            return false;
        }
        *x13 *= x11;
    }
    return true;
}
static bool x15(uint64_t x16, x3* x17) {
    uint64_t x18;
    if (!x10(x2, x16, &x18)) {
        return false;
    }
    char x19[x0];
    for (uint64_t x14 = 0; x14 < x18; ++x14) {
        uint64_t x20 = x14;
        for (int64_t x21 = x16 - 1; x21 >= 0; --x21) {
            uint64_t x22 = x20 % x2;
            x19[x21] = x1[x22];
            x20 /= x2;
        }
        if (!x17->x5(x17->x4, x19, x16)) {
            return false;
        }
        if (!x17->x8(x17->x4, '\n')) {
            return false;
        }
    }
    return true;
}
static bool x23(void* x4, const char* x6, uint64_t x7) {
    FILE* x24 = (FILE*)x4;
    return fwrite(x6, sizeof(char), x7, x24) == x7;
}
static bool x25(void* x4, char x9) {
    FILE* x24 = (FILE*)x4;
    return fputc(x9, x24) != EOF;
}
static bool x26(x3* x17, const char* x27) {
    FILE* x24 = fopen(x27, "w");
    if (x24 == NULL) {
        return false;
    }
    *x17 = (x3){
        .x4 = x24,
        .x5 = x23,
        .x8 = x25
    };
    return true;
}
static void x28(x3* x17) {
    if (x17 && x17->x4) {
        fclose((FILE*)x17->x4);
        x17->x4 = NULL;
    }
}
int main(void) {
    const uint64_t x30 = 7;
    if (x30 == 0 || x30 > x0) {
        return 1;
    }
    x3 x31;
    if (!x26(&x31, "x33.txt")) {
        perror("Error opening file");
        return 1;
    }
    bool x32 = x15(x30, &x31);
    x28(&x31);
    if (!x32) {
        return 1;
    }
    return 0;
}