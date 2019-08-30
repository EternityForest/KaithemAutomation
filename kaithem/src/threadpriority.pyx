cdef extern from "<pthread.h>":    
    cdef struct sched_param:
        int sched_priority

    ctypedef int pthread_t

    int pthread_setschedparam(pthread_t thread, int policy,  sched_param *param)
	
    int pthread_self()


cpdef setThreadPriority(int policy, int priority):
    cdef sched_param param
    cdef pthread_t x

    param.sched_priority = priority
    x = pthread_self()
    pthread_setschedparam(x, policy, &param)
