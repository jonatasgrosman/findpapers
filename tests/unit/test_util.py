from findpapers import util as Util

def test_get_numeric_month_by_string():

    assert Util.get_numeric_month_by_string('december') == '12'
    
    assert Util.get_numeric_month_by_string('february') == '02'
    