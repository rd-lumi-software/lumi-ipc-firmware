/* Baremetal newlib heap is bounded below a separately reserved64KiB stack. */
#include <stddef.h>
#include <errno.h>
extern char __heap_start[], __heap_end[];
void *_sbrk(ptrdiff_t increment)
{
 static char *current;
 if (!current) current = __heap_start;
 if (increment < 0 || (size_t)increment > (size_t)(__heap_end-current)) {
  errno = ENOMEM;
  return (void *)-1;
 }
 char *result = current;
 current += increment;
 return result;
}
