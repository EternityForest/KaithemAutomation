# SPDX-FileCopyrightText: Copyright 2018 Daniel Dunn
# SPDX-License-Identifier: GPL-3.0-only


def breakpoint():
    """This function exists entirely for debugging user code in background threads.
    Call this function whenever you want to break, and set a breakpoint on the function you want to debug"""
    print("breakpoint.breakpoint has been called")
