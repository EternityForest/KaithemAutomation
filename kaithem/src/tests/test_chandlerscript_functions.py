from kaithem.src import scriptbindings


def test_onchange():
    ctx = scriptbindings.ChandlerScriptContext()

    b = scriptbindings.OnChangeBlock(ctx)

    assert b.call(78778) is None
    assert b.call(78778) is None
    assert b.call(78780) == 78780
    assert b.call(78781) == 78781
    assert b.call(78781) is None


def test_on_rising_edge():
    ctx = scriptbindings.ChandlerScriptContext()

    b = scriptbindings.OnRisingEdgeBlock(ctx)

    assert b.call(1) is None
    assert b.call(1) is None
    assert b.call(0) is None
    assert b.call(0) is None
    assert b.call(1) == 1
    assert b.call(1) is None
    assert b.call(0) is None
    assert b.call(1) == 1


def test_on_counter_block():
    ctx = scriptbindings.ChandlerScriptContext()

    b = scriptbindings.OnCounterIncreaseBlock(ctx)

    assert b.call(0) is None
    assert b.call(0) is None
    assert b.call(1) == 1
    assert b.call(1) is None
    assert b.call(0) is None

    assert b.call(1) == 1
    assert b.call(2) == 2
    assert b.call(3) == 3

    assert b.call(2) is None
    # Large increase
    assert b.call(1000000) == 1000000
    #  Very large decrease assumed to be wraparound
    assert b.call(1) == 1


def test_hysteresis_block():
    ctx = scriptbindings.ChandlerScriptContext()
    b = scriptbindings.HysteresisBlock(ctx)

    assert b.call(0, window=1) is None
    assert b.call(0, window=1) is None
    assert b.call(0.1, window=1) is None
    assert b.call(0.6, window=1) == 0.6
    assert b.call(0.7, window=1) == 0.7
    assert b.call(0.8, window=1) == 0.8
    assert b.call(0.6, window=1) is None
    assert b.call(0.1, window=1) == 0.1
    assert b.call(0, window=1) == 0
    assert b.call(49, window=100) is None

    assert b.call(50, window=100) == 50
    assert b.call(51, window=100) == 51
    assert b.call(30, window=100) is None

    assert b.call(-100, window=100) == -100
