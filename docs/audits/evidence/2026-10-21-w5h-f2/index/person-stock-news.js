//主要指标
var mainIndicators_mixin = {
    data: {
        mainIndicatorsActiveIndex: '全部',
        datearr3: [],
        arrall: [],//全部
        arr31: [],//year
        arr32: [],//three
        arr33: [],//middle
        arr34: [],//one
        reflect: {'全部': 'arrall', '年报': 'arr31', '三季报': 'arr32', '中报': 'arr33', '一季报': 'arr34',},
        arrone: [],//主要指标
        arrtwo: [],//偿债能力指标
        arrthree: [],//one
        arrfour: [],//one
        arrfive: [],//one
        mainIndicatorsTableData: []
    },
    methods: {
        mainIndicatorsMount: function () {
            var _this = this;
            if (!this.sign) {
                axios({
                    url: cninfo_data20 + '/companyOverview/getCompanyInfo',
                    method: 'get',
                    params: {
                        scode: stockCode
                    }
                }).then(function (res) {
                    if (res.code != 200 || res.data.resultMsg != "success") {
                        return;
                    }
                    if (res.data.records.length > 0) {
                        var sign = res.data.records[0].F002N
                        _this.sign = sign;
                        if (sign) {
                            _this.mainIndicatorsMount2(sign)
                        }
                    }
                }).catch(function () {
                    _this.isTimeLoading = false;
                })
            } else {
                _this.mainIndicatorsMount2(_this.sign)
            }
        },
        mainIndicatorsMount2: function (sign) {
            var _this = this;
            _this.isTimeLoading = true;
            axios({
                url: cninfo_data20 + '/financialData/getMainIndicators',
                method: 'get',
                params: {
                    scode: stockCode,
                    sign: sign,
                }
            }).then(function (res) {
                _this.isTimeLoading = false;
                if (res.code != 200 || res.data.resultMsg != "success") {
                    return;
                }
                if (res.data.records.length > 0) {
                    var arr = res.data.records[0];
                    _this.arr31 = arr.year;
                    _this.arr32 = arr.three;
                    _this.arr33 = arr.middle;
                    _this.arr34 = arr.one;
                    _this.arrall = arr.one.concat(arr.middle, arr.three, arr.year);
                    _this.mainIndicatorsDatefilter(_this.arrall)
                }
            }).catch(function () {
                _this.isTimeLoading = false;
            })
        },
        //给某行表格字体加粗
        mainIndicatorsRowClass: function (scope) {
            if (scope.rowIndex == 0 || scope.rowIndex == 7 || scope.rowIndex == 11 || scope.rowIndex == 17 || scope.rowIndex == 22) {
                return 'addWeight'
            }
            return '';
        },
        dateChangeBtn3: function (v) {
            var deepcopy = JSON.parse(JSON.stringify(this[this.reflect[v]]));
            this.mainIndicatorsDatefilter(deepcopy);
        },
        sort: function (arr) {
            for (var i = 0; i < arr.length - 1; i++) {
                for (var j = 0; j < arr.length - i - 1; j++) {
                    if (arr[j] < arr[j + 1]) {
                        var swap = arr[j];
                        arr[j] = arr[j + 1];
                        arr[j + 1] = swap;
                    }
                }
            }
            return arr;
        },
        forSortDate: function (arr) {
            var brr = arr.map(function (item) {
                return new Date(item) * 1;
            })
            this.datearr3 = this.sort(brr).slice(0, 5)
                .map(function (item) {
                    return fomatDate(item, 'yyyy-MM-dd');
                })
            this.datearr3.unshift('');
        },
        mainIndicatorsDatefilter: function (arr) {
            this.datearr3 = [];
            var _this = this;
            arr.forEach(function (item) {
                _this.datearr3.push(item.ENDDATE);
            })
            _this.forSortDate(_this.datearr3);
            // 为了让日期从大往小排列  并且取5个
            var renderArray = []
            var f = [
                ['主要指标', null],
                ['基本每股收益(元)', 'F004N'],
                ['每股净资产(元)', 'F008N'],
                ['每股资本公积金(元)', 'F010N'],
                ['净利润增长率(%)', 'F053N'],
                ['营业总收入增长率(%)', 'F052N'],
                ['加权净资产收益率(%)', 'F067N'],

                ['偿还能力指标', null],
                ['流动比率', 'F042N'],
                ['速动比率', 'F043N'],
                ['资产负债比率(%)', 'F041N'],

                ['运营能力指标', null],
                ['应收账款周转率(次)', 'F022N'],
                ['存货周转率(次)', 'F023N'],
                ['流动资产周转率(次)', 'F029N'],
                ['固定资产周转率(次)', 'F026N'],
                ['总资产周转率(次)', 'F025N'],

                ['盈利能力指标', null],
                ['营业利润率(%)', 'F011N'],
                ['净利润率(%)', 'F017N'],
                ['毛利率(%)', 'F078N'],
                ['总资产报酬率(%)', 'F016N'],

                ['发展能力指标', null],
                ['营业收入增长率(%)', 'F052N'],
                ['总资产增长率(%)', 'F056N'],
                ['营业利润增长率(%)', 'F058N'],
                ['净利润增长率(%)', 'F053N'],
                ['净资产增长率(%)', 'F054N'],
            ]
            for (var j = 0; j < f.length; j++) {
                var obj = {};
                for (var i = 0; i < _this.datearr3.length; i++) {
                    if (i > 0 && i < _this.datearr3.length) {
                        var crr = arr.filter(function (item) {
                            return item.ENDDATE == _this.datearr3[i];
                        });
                        obj['prop' + (i + 1)] = f[j][1] ? Number(crr[0][f[j][1]]).toFixed(2) : '-';
                    } else {
                        obj.prop1 = f[j][0];
                    }
                }
                renderArray.push(obj);
            }
            _this.mainIndicatorsTableData = renderArray;
        }
    }
}
var plateCode = plate;
var cookieUserName = 'cninfo_user_browse'; //巨潮用户
//财务报表
var financialStatements_mixin = {
    data: {
        aisTimeLoading: true,
        bisTimeLoading: true,
        cisTimeLoading: true,
        aFinanObj1: {
            aTypereflect1: {
                '-12-31': 'aArray1',
                '-09-30': 'aArray2',
                '-06-30': 'aArray3',
                '-03-31': 'aArray4'
            },
            aArray1: [],
            aArray2: [],
            aArray3: [],
            aArray4: [],
            aFinancialStatementsActiveIndex: '全部',
            aDatearr4: [],
            aReflect: {'年报': 'aArray1', '三季报': 'aArray2', '中报': 'aArray3', '一季报': 'aArray4',},
            aFinancialStatementsTableData: [],
        },
        bFinanObj1: {
            bTypereflect1: {
                '-12-31': 'bArray1',
                '-09-30': 'bArray2',
                '-06-30': 'bArray3',
                '-03-31': 'bArray4'
            },
            bArray1: [],
            bArray2: [],
            bArray3: [],
            bArray4: [],
            bFinancialStatementsActiveIndex: '全部',
            bDatearr4: [],
            bReflect: {'年报': 'bArray1', '三季报': 'bArray2', '中报': 'bArray3', '一季报': 'bArray4'},
            bFinancialStatementsTableData: [],
        },
        cFinanObj1: {
            cTypereflect1: {
                '-12-31': 'cArray1',
                '-09-30': 'cArray2',
                '-06-30': 'cArray3',
                '-03-31': 'cArray4'
            },
            cArray1: [],
            cArray2: [],
            cArray3: [],
            cArray4: [],
            cFinancialStatementsActiveIndex: '全部',
            cDatearr4: [],
            cReflect: {'年报': 'cArray1', '三季报': 'cArray2', '中报': 'cArray3', '一季报': 'cArray4'},
            cFinancialStatementsTableData: [],
        },
    },
    methods: {
        //第1部分函数集合
        financialStatementsMount: function () {
            var _this = this;
            if (!this.sign) {
                axios({
                    url: cninfo_data20 + '/companyOverview/getCompanyInfo',
                    method: 'get',
                    params: {
                        scode: stockCode
                    }
                }).then(function (res) {
                    if (res.code != 200 || res.data.resultMsg != "success") {
                        return;
                    }
                    if (res.data.records.length > 0) {
                        var sign = res.data.records[0].F002N;
                        _this.sign = sign;
                        if (sign) {
                            _this.aFinancialStatementsMount(sign);
                            _this.bFinancialStatementsMount(sign);
                            _this.cFinancialStatementsMount(sign);
                        }
                    }
                }).catch(function () {
                    _this.aisTimeLoading = false;
                    _this.bisTimeLoading = false;
                    _this.cisTimeLoading = false;
                })
            } else {
                _this.aFinancialStatementsMount(_this.sign);
                _this.bFinancialStatementsMount(_this.sign);
                _this.cFinancialStatementsMount(_this.sign);
            }
        },
        echartPie: function (arr, brr, id) {
            arr.reverse();
            brr.reverse();
            var len = arr.length - 1;
            var myChart = echarts.init(document.getElementById(id));
            var option = {
                grid: {
                    x: 0,
                    y: 30,
                    x2: 0,
                    y2: 30
                },
                tooltip: {
                    trigger: 'axis',
                    axisPointer: {
                        type: 'none'
                    }
                },
                visualMap: {
                    show: false,
                    pieces: [{gt: 0, color: '#05c'}, {lt: 0, color: '#1f9939'}],
                    dimension: 1
                },
                xAxis: {
                    type: "category",
                    data: arr,
                    axisTick: {show: false},
                    axisLine: {show: false},
                    axisLabel: {
                        interval: 0,
                        margin: 15
                    }
                },
                yAxis: {
                    splitLine: {show: false},
                    axisTick: {show: false},
                    axisLine: {show: false},
                    axisLabel: {show: false}
                },
                series: [{
                    type: 'pictorialBar',
                    barWidth: 105,
                    barCategoryGap: '0',
                    itemStyle: {
                        fontSize: 14,
                        // color: '#ffc956'
                    },
                    label: {
                        fontSize: 14,
                        show: true,
                        color: '#1d2023',
                        position: 'top',
                    },
                    symbol: 'path://M 337.93 225.07 C 314.79 115.13 302.64 80.82 283.46 82.86 c -19.17 -2 -31.32 32.27 -54.46 142.21 C 191.3 404.13 62.83 466.2 0 484.15 H 566.93 C 504.1 466.2 375.63 404.13 337.93 225.07 Z',
                    data: brr
                }]
            };

            myChart.setOption(option)
        },
        financialStatementsCellClass: function (scope) {
            var columnIndex = scope.columnIndex;
            if (columnIndex == '0') {
                return 'firstcol'
            }
            return ''
        },
        //利润表
        aFinancialStatementsMount: function (sign) {
            var _this = this;
            _this.aisTimeLoading = true;
            axios({
                url: cninfo_data20 + '/financialData/getIncomeStatement',
                method: 'get',
                params: {
                    scode: stockCode,
                    sign: sign,
                }
            }).then(function (res) {
                _this.aisTimeLoading = false;
                if (res.code != 200 || res.data.resultMsg != "success") {
                    return;
                }
                if (res.data.records.length > 0) {
                    var arr = res.data.records[0];
                    _this.aFinanObj1.aArray1 = _this.aYearThreeMiddleOne(arr.year, '-12-31');
                    _this.aFinanObj1.aArray2 = _this.aYearThreeMiddleOne(arr.three, '-09-30');
                    _this.aFinanObj1.aArray3 = _this.aYearThreeMiddleOne(arr.middle, '-06-30');
                    _this.aFinanObj1.aArray4 = _this.aYearThreeMiddleOne(arr.one, '-03-31');
                    _this.aClickAll(true);
                    _this.aClickOther("年报", true);
                }
            }).catch(function () {
                _this.aisTimeLoading = false;
            })
        },
        aClickOther: function (v, isFirstTime) {
            var _this = this;
            var deepcopy = JSON.parse(JSON.stringify(this.aFinanObj1[this.aFinanObj1.aReflect[v]]));
            //是否有数据
            if (!!!deepcopy[0].index) {
                this.aFinanObj1.aDatearr4 = [];
                this.aFinanObj1.aFinancialStatementsTableData = [];
                return;
            }
            var deparr = Object.keys(deepcopy[0]);
            var index = deparr.indexOf('index');
            deparr.splice(index, 1);
            deparr.reverse()
            deparr.unshift('')
            var renderArr = [];
            for (var i = 0; i < deepcopy.length; i++) {
                var rObjItem = {};
                for (var j = 0; j < deparr.length; j++) {
                    if (j > 0) {
                        rObjItem['prop' + (j + 1)] = deepcopy[i][deparr[j]];
                    } else {
                        rObjItem.prop1 = deepcopy[i].index;
                    }
                }
                renderArr.push(rObjItem);
            }
            if (isFirstTime) {
                this.aFinanObj1.aYearDate = deparr;
                this.aFinanObj1.aYearData = renderArr;
                _this.yysrAndLirun('pie1', '营业,收入');
                _this.yysrAndLirun('pie2', '净利,润');
            } else {
                this.aFinanObj1.aDatearr4 = deparr;
                this.aFinanObj1.aFinancialStatementsTableData = renderArr;
            }
        },
        aClickAll: function () {
            var _this = this;
            var objkeyarr = Object.keys(_this.aFinanObj1.aArray1[0]).concat(Object.keys(_this.aFinanObj1.aArray2[0]), Object.keys(_this.aFinanObj1.aArray3[0]), Object.keys(_this.aFinanObj1.aArray4[0]))
            var aRemoveRepeatIndexArr = _this.aRemoveRepeat(objkeyarr);
            var index = aRemoveRepeatIndexArr.indexOf('index');
            aRemoveRepeatIndexArr.splice(index, 1);
            _this.aForSortDate4(aRemoveRepeatIndexArr);
            var renderArr = [];
            for (var i = 0; i < _this.aFinanObj1.aArray1.length; i++) {
                var rObjItem = {};
                for (var j = 0; j < _this.aFinanObj1.aDatearr4.length; j++) {
                    if (j > 0) {
                        var str = _this.aFinanObj1.aDatearr4[j];
                        //根据日期的月日  对应到数组
                        var monthday = str.slice(4);
                        var typeArr = _this.aFinanObj1[_this.aFinanObj1.aTypereflect1[monthday]];
                        rObjItem['prop' + (j + 1)] = typeArr[i][str];
                    } else {
                        rObjItem.prop1 = _this.aFinanObj1.aArray1[i].index;
                    }
                }
                renderArr.push(rObjItem)
            }
            _this.aFinanObj1.aFinancialStatementsTableData = renderArr;

        },
        yysrAndLirun: function (id, param) {
            var brr = [];
            var arr = this.aFinanObj1.aYearDate.slice(1);
            var one = param.split(',');
            var _brr = this.aFinanObj1.aYearData.filter(function (item) {
                return item.prop1.indexOf(one[0]) > -1 && item.prop1.indexOf(one[1]) > -1;
            })
            var keys = Object.keys(_brr[0]);
            keys.forEach(function (item) {
                if (item != 'prop1' && _brr[0][item]) {
                    brr.push(_brr[0][item]);
                }
            })
            this.echartPie(arr, this.unitTransform(brr), id);
        },
        //单位换算 万元转换为亿元 用四舍五入法则
        unitTransform: function (arr) {
            if (arr.length > 0) {
                var brr = arr.map(function (item) {
                    return (Number(item) / 10000).toFixed(2);
                })
                return brr;
            }
        },
        aRemoveRepeat: function (arr) {
            var brr = [];
            arr.forEach(function (item) {
                if (brr.indexOf(item) == -1) {
                    brr.push(item)
                }
            })
            return brr;
        },
        aYearThreeMiddleOne: function (arr, type) {
            if (arr.length == 0) {
                return [{}];
            }
            return arr.map(function (item) {
                var obj = {};
                for (var key in item) {
                    if (key != 'index') {
                        obj[key + type] = item[key];
                    } else {
                        obj[key] = item[key];
                    }
                }
                return obj;
            })
        },
        aDateChangeBtn4: function (v) {
            if (v == '全部') {
                this.aClickAll();
            } else {
                this.aClickOther(v);
            }

        },
        aSort4: function (arr) {
            for (var i = 0; i < arr.length - 1; i++) {
                for (var j = 0; j < arr.length - i - 1; j++) {
                    if (arr[j] < arr[j + 1]) {
                        var swap = arr[j];
                        arr[j] = arr[j + 1];
                        arr[j + 1] = swap;
                    }
                }
            }
            return arr;
        },
        aForSortDate4: function (arr) {
            var brr = arr.map(function (item) {
                return new Date(item) * 1;
            })
            this.aFinanObj1.aDatearr4 = this.aSort4(brr).slice(0, brr.length > 5 ? 5 : brr.length).map(function (item) {
                return fomatDate(item, 'yyyy-MM-dd');
            })
            this.aFinanObj1.aDatearr4.unshift('');
        },

        //现金流量表
        bFinancialStatementsMount: function (sign) {
            var _this = this;
            _this.bisTimeLoading = true;
            axios({
                url: cninfo_data20 + '/financialData/getCashFlowStatement',
                method: 'get',
                params: {
                    scode: stockCode,
                    sign: sign,
                }
            }).then(function (res) {
                _this.bisTimeLoading = false;
                if (res.code != 200 || res.data.resultMsg != "success") {
                    return;
                }
                if (res.data.records.length > 0) {
                    var arr = res.data.records[0];
                    _this.bFinanObj1.bArray1 = _this.bYearThreeMiddleOne(arr.year, '-12-31');
                    _this.bFinanObj1.bArray2 = _this.bYearThreeMiddleOne(arr.three, '-09-30');
                    _this.bFinanObj1.bArray3 = _this.bYearThreeMiddleOne(arr.middle, '-06-30');
                    _this.bFinanObj1.bArray4 = _this.bYearThreeMiddleOne(arr.one, '-03-31');
                    _this.bClickAll();
                }
            }).catch(function () {
                _this.bisTimeLoading = false;
            })
        },
        bClickOther: function (v) {
            var deepcopy = JSON.parse(JSON.stringify(this.bFinanObj1[this.bFinanObj1.bReflect[v]]));
            if (!!!deepcopy[0].index) {
                this.bFinanObj1.bDatearr4 = [];
                this.bFinanObj1.bFinancialStatementsTableData = [];
                return
            }
            var deparr = Object.keys(deepcopy[0]);
            var index = deparr.indexOf('index');
            deparr.splice(index, 1);
            deparr.reverse()
            deparr.unshift('')
            this.bFinanObj1.bDatearr4 = deparr;
            var len = deepcopy.length;
            var renderArr = [];
            for (var i = 0; i < len; i++) {
                var rObjItem = {};
                for (var j = 0; j < 6; j++) {
                    if (j > 0) {
                        rObjItem['prop' + (j + 1)] = deepcopy[i][this.bFinanObj1.bDatearr4[j]];
                    } else {
                        rObjItem.prop1 = deepcopy[i].index;
                    }
                }
                renderArr.push(rObjItem);
            }
            this.bFinanObj1.bFinancialStatementsTableData = renderArr;
        },
        bClickAll: function () {
            var _this = this;
            var objkeyarr = Object.keys(_this.bFinanObj1.bArray1[0]).concat(Object.keys(_this.bFinanObj1.bArray2[0]), Object.keys(_this.bFinanObj1.bArray3[0]), Object.keys(_this.bFinanObj1.bArray4[0]))
            var bRemoveRepeatIndexArr = _this.bRemoveRepeat(objkeyarr);
            var index = bRemoveRepeatIndexArr.indexOf('index');
            bRemoveRepeatIndexArr.splice(index, 1);
            _this.bForSortDate4(bRemoveRepeatIndexArr);
            var renderArr = [];
            for (var i = 0; i < _this.bFinanObj1.bArray1.length; i++) {
                var rObjItem = {};
                for (var j = 0; j < _this.bFinanObj1.bDatearr4.length; j++) {
                    if (j > 0) {
                        var str = _this.bFinanObj1.bDatearr4[j];
                        var monthday = str.slice(4);
                        var typeArr = _this.bFinanObj1[_this.bFinanObj1.bTypereflect1[monthday]];
                        rObjItem['prop' + (j + 1)] = typeArr[i][str];
                    } else {
                        rObjItem.prop1 = _this.bFinanObj1.bArray1[i].index;
                    }
                }
                renderArr.push(rObjItem)
            }
            _this.bFinanObj1.bFinancialStatementsTableData = renderArr;
        },
        bRemoveRepeat: function (arr) {
            var brr = [];
            arr.forEach(function (item) {
                if (brr.indexOf(item) == -1) {
                    brr.push(item)
                }
            })
            return brr;
        },
        bYearThreeMiddleOne: function (arr, type) {
            if (arr.length == 0) {
                return [{}];
            }
            return arr.map(function (item) {
                var obj = {};
                for (var key in item) {
                    if (key != 'index') {
                        obj[key + type] = item[key];
                    } else {
                        obj[key] = item[key];
                    }
                }
                return obj;
            })
        },
        bDateChangeBtn4: function (v) {
            if (v == '全部') {
                this.bClickAll();
            } else {
                this.bClickOther(v);
            }
        },
        bSort4: function (arr) {
            for (var i = 0; i < arr.length - 1; i++) {
                for (var j = 0; j < arr.length - i - 1; j++) {
                    if (arr[j] < arr[j + 1]) {
                        var swap = arr[j];
                        arr[j] = arr[j + 1];
                        arr[j + 1] = swap;
                    }
                }
            }
            return arr;
        },
        bForSortDate4: function (arr) {
            var brr = arr.map(function (item) {
                return new Date(item) * 1;
            })
            this.bFinanObj1.bDatearr4 = this.bSort4(brr).slice(0, brr.length > 5 ? 5 : brr.length).map(function (item) {
                return fomatDate(item, 'yyyy-MM-dd');
            })
            this.bFinanObj1.bDatearr4.unshift('');
        },

        //资产负债表
        cFinancialStatementsMount: function (sign) {
            var _this = this;
            _this.cisTimeLoading = true;
            axios({
                url: cninfo_data20 + '/financialData/getBalanceSheets',
                method: 'get',
                params: {
                    scode: stockCode,
                    sign: sign,
                }
            }).then(function (res) {
                _this.cisTimeLoading = false;
                if (res.code != 200 || res.data.resultMsg != "success") {
                    return;
                }
                if (res.data.records.length > 0) {
                    var arr = res.data.records[0];
                    _this.cFinanObj1.cArray1 = _this.cYearThreeMiddleOne(arr.year, '-12-31');
                    _this.cFinanObj1.cArray2 = _this.cYearThreeMiddleOne(arr.three, '-09-30');
                    _this.cFinanObj1.cArray3 = _this.cYearThreeMiddleOne(arr.middle, '-06-30');
                    _this.cFinanObj1.cArray4 = _this.cYearThreeMiddleOne(arr.one, '-03-31');
                    _this.cClickAll();
                }
            }).catch(function () {
                _this.cisTimeLoading = false;
            })
        },
        //给不定行表格 字体加粗
        cFinancialStatementsCellClass: function (scope) {
            var row = scope.row;
            var columnIndex = scope.columnIndex;
            if (row.prop1 == '资产类科目'
                || row.prop1 == '负债类科目'
                || row.prop1 == '股东权益类科目'
                || row.prop1 == '股东权益类科目'
            ) {
                return 'addWeight'
            }
            return ''

        },
        cClickOther: function (v) {
            var deepcopy = JSON.parse(JSON.stringify(this.cFinanObj1[this.cFinanObj1.cReflect[v]]));
            if (!!!deepcopy[0].index) {
                this.cFinanObj1.cDatearr4 = [];
                this.cFinanObj1.cFinancialStatementsTableData = []
                return;
            }
            var deparr = Object.keys(deepcopy[0]);
            var index = deparr.indexOf('index');
            deparr.splice(index, 1);
            deparr.reverse();
            deparr.unshift('');
            this.cFinanObj1.cDatearr4 = deparr;
            var len = deepcopy.length;
            var renderArr = [];
            for (var i = 0; i < len; i++) {
                var rObjItem = {};
                for (var j = 0; j < 6; j++) {
                    if (j > 0) {
                        rObjItem['prop' + (j + 1)] = deepcopy[i][this.cFinanObj1.cDatearr4[j]];
                    } else {
                        rObjItem.prop1 = deepcopy[i].index;
                    }
                }
                renderArr.push(rObjItem);
            }
            this.cFinanObj1.cFinancialStatementsTableData = renderArr;
        },
        cClickAll: function () {
            var _this = this;
            var objkeyarr = Object.keys(_this.cFinanObj1.cArray1[0]).concat(Object.keys(_this.cFinanObj1.cArray2[0]), Object.keys(_this.cFinanObj1.cArray3[0]), Object.keys(_this.cFinanObj1.cArray4[0]))
            var cRemoveRepeatIndexArr = _this.cRemoveRepeat(objkeyarr);
            var index = cRemoveRepeatIndexArr.indexOf('index');
            cRemoveRepeatIndexArr.splice(index, 1);
            _this.cForSortDate4(cRemoveRepeatIndexArr);
            var renderArr = [];
            for (var i = 0; i < _this.cFinanObj1.cArray1.length; i++) {
                var rObjItem = {};
                for (var j = 0; j < _this.cFinanObj1.cDatearr4.length; j++) {
                    if (j > 0) {
                        var str = _this.cFinanObj1.cDatearr4[j];
                        var monthday = str.slice(4);
                        var typeArr = _this.cFinanObj1[_this.cFinanObj1.cTypereflect1[monthday]];
                        rObjItem['prop' + (j + 1)] = typeArr[i][str];
                    } else {
                        rObjItem.prop1 = _this.cFinanObj1.cArray1[i].index;
                    }
                }
                renderArr.push(rObjItem)
            }
            _this.cFinanObj1.cFinancialStatementsTableData = renderArr;
        },
        cRemoveRepeat: function (arr) {
            var brr = [];
            arr.forEach(function (item) {
                if (brr.indexOf(item) == -1) {
                    brr.push(item)
                }
            })
            return brr;
        },
        cYearThreeMiddleOne: function (arr, type) {
            if (arr.length == 0) {
                return [{}]
            }
            return arr.map(function (item) {
                var obj = {};
                for (var key in item) {
                    if (key != 'index') {
                        obj[key + type] = item[key] ? item[key] : '-';
                    } else {
                        obj[key] = item[key] ? item[key] : '-';
                    }
                }
                return obj;
            })
        },
        cDateChangeBtn4: function (v) {
            if (v == '全部') {
                this.cClickAll();
            } else {
                this.cClickOther(v);
            }
        },
        cSort4: function (arr) {
            for (var i = 0; i < arr.length - 1; i++) {
                for (var j = 0; j < arr.length - i - 1; j++) {
                    if (arr[j] < arr[j + 1]) {
                        var swap = arr[j];
                        arr[j] = arr[j + 1];
                        arr[j + 1] = swap;
                    }
                }
            }
            return arr;
        },
        cForSortDate4: function (arr) {
            var brr = arr.map(function (item) {
                return new Date(item) * 1;
            })
            this.cFinanObj1.cDatearr4 = this.cSort4(brr).slice(0, brr.length > 5 ? 5 : brr.length).map(function (item) {
                return fomatDate(item, 'yyyy-MM-dd');
            })
            this.cFinanObj1.cDatearr4.unshift('');
        },
    }
}

//公司高管
var executivest_mixin = {
    data: {
        dialogVisible: '',
        executivestTableData: [],
        executivestObj: {
            executivestTableData: [],
            size: 20,
            total: 0,
            pageExecutivestData: [],
            num: 1
        },
        allemptystr: '',
        executivestMsg: {
            jobonduty: []
        }
    },
    methods: {
        executivestMount: function () {
            this.axiosExecutivest();
        },
        toDate: function (servingdate, departdate) {
            if (servingdate && departdate) {
                return fomatDate(Number(servingdate), 'yyyy-MM-dd') + ' 至 ' + fomatDate(Number(departdate), 'yyyy-MM-dd');
            } else {
                return fomatDate(Number(servingdate), 'yyyy-MM-dd') + ' 至今';
            }
        },
        //前端分页处理
        executivestPageChange: function (num) {
            this.executivestObj.pageExecutivestData = this.executivestObj.executivestTableData.slice(20 * num - 20, 20 * num);
        },
        axiosExecutivest: function () {
            var _this = this;
            _this.isTimeLoading = true;
            axios({
                url: cninfo_data20 + '/companyOverview/getCompanyExecutives',
                method: 'get',
                params: {
                    scode: stockCode
                }
            }).then(function (res) {
                _this.isTimeLoading = false;
                if (res.code != 200 && res.data.resultMsg != 'success') {
                    return;
                }
                if (res.data.records.length > 0) {
                    _this.executivestObj.executivestTableData = res.data.records;
                    _this.executivestObj.total = res.data.records.length;
                    _this.executivestPageChange(1);
                }
            }).catch(function () {
                _this.isTimeLoading = false;
            })
        },
        findDetail: function (row) {
            var _this = this;
            axios({
                url: path + '/executive/detail',
                method: 'get',
                params: {
                    stockcode: stockCode,
                    humanId: row.F001V
                }
            }).then(function (res) {
                _this.dialogVisible = row.F002V;
                if (res) {
                    _this.executivestMsg = res;
                    _this.allemptystr = '';
                } else {
                    _this.executivestMsg = {
                        jobonduty: []
                    };
                    _this.allemptystr = '暂无数据';
                }
            })
        },
        adddouhao: function (item) {
            if (item.F005N == '--') {
                return '--'
            } else {
                return this.addfengefu(item.F005N, 0);
            }
        }
    }
}
//历史分红
var historicalDividend_mixin = {
    data: {
        historicalDividendObj: {
            historicalDividendTableData: [],
            size: 20,
            total: 0,
            pageHistoricalDividendData: [],
            num: 1
        },
        historicalDividendTableData: []
    },
    methods: {
        historicalDividendMount: function () {
            this.axiosHistoricalDividend()
        },
        axiosHistoricalDividend: function () {
            var _this = this;
            _this.isTimeLoading = true;
            axios({
                url: cninfo_data20 + '/companyOverview/getCompanyHisDividend',
                method: 'get',
                params: {
                    scode: stockCode
                }
            }).then(function (res) {
                _this.isTimeLoading = false;
                if (res.code != 200 || res.data.resultMsg != 'success') {
                    return;
                }

                if (res.data.records.length > 0) {
                    _this.historicalDividendObj.historicalDividendTableData = res.data.records;
                    _this.historicalDividendObj.total = res.data.records.length;
                    _this.historicalDividendPageChange(1);
                }
                _this.historicalDividendTableData = res.data.records;
            }).catch(function () {
                _this.isTimeLoading = false;
            })
        },
        //前端分页处理
        historicalDividendPageChange: function (num) {
            this.historicalDividendObj.pageHistoricalDividendData = this.historicalDividendObj.historicalDividendTableData.slice(20 * num - 20, 20 * num);
        },
    }
}

//最新公告 || 定期报告 || 调研 || 摘要
var latestAnnouncement_mixin = {
    data: {
        actSecname: '',
        tabType: 'fulltext',  //默认公告
        oldTab: 'fulltext',  //tab点击之前,tab类型
        plateType: plate,
        pageNum: 1,
        pageSize: 30,
        category: [],    //分类类别
        categoryString: '',
        chekedCategory: [],  //选中分类列表
        fulltextAndSummary: [], /*公告，摘要 分类*/
        relationType: [],    /*调研 分类*/
        periodType: [], /*定期公告*/
        newList: [],
        totalNum: 0,
        totalNumReal: 0,
        keyWords: '',
        keyWordsArray: [], /*关键字列表*/
        keyWordString: '',
        sortName: '', /*排序类别*/
        sortType: '', /*升降序*/
        date: '',
        codelist: plate == 'szse' ? 'sz' : plate == 'sse' ? 'sh': plate == 'bj' ? 'bj;third' : plate, /*深市sz, 沪市sh,其他空*/
        pickerOption: {
            disabledDate: function (time) {
                return time.getTime() < new Date("1999-12-31")
            },
            shortcuts: [{
                text: '明日',
                onClick: function (picker) {
                    var end = new Date();
                    var start = new Date();
                    end.setTime(start.getTime() + 3600 * 1000 * 24 * 1);
                    picker.$emit('pick', [end, end]);
                }
            }, {
                text: '今日',
                onClick: function (picker) {
                    var end = new Date();
                    var start = new Date();
                    picker.$emit('pick', [start, end]);
                }
            }, {
                text: '近1周',
                onClick: function (picker) {
                    var end = new Date();
                    var start = new Date();
                    start.setTime(start.getTime() - 3600 * 1000 * 24 * 7);
                    if (end.getHours() >= 15) {
                        end.setTime(end.getTime() + 3600 * 1000 * 24);
                    }
                    picker.$emit('pick', [start, end]);
                }
            }, {
                text: '近1月',
                onClick: function (picker) {
                    var end = new Date();
                    var start = new Date();
                    start.setTime(start.getTime() - 3600 * 1000 * 24 * 30);
                    if (end.getHours() >= 15) {
                        end.setTime(end.getTime() + 3600 * 1000 * 24);
                    }
                    picker.$emit('pick', [start, end]);
                }
            }, {
                text: '近3月',
                onClick: function (picker) {
                    var end = new Date();
                    var start = new Date();
                    start.setTime(start.getTime() - 3600 * 1000 * 24 * 90);
                    if (end.getHours() >= 15) {
                        end.setTime(end.getTime() + 3600 * 1000 * 24);
                    }
                    picker.$emit('pick', [start, end]);
                }
            }, {
                text: '近6月',
                onClick: function (picker) {
                    var end = new Date();
                    var start = new Date();
                    start.setTime(start.getTime() - 3600 * 1000 * 24 * 180);
                    if (end.getHours() >= 15) {
                        end.setTime(end.getTime() + 3600 * 1000 * 24);
                    }
                    picker.$emit('pick', [start, end]);
                }
            }, {
                text: '近1年',
                onClick: function (picker) {
                    var end = new Date();
                    var start = new Date();
                    start.setTime(start.getTime() - 3600 * 1000 * 24 * 365);
                    if (end.getHours() >= 15) {
                        end.setTime(end.getTime() + 3600 * 1000 * 24);
                    }
                    picker.$emit('pick', [start, end]);
                }
            }, {
                text: '近3年',
                onClick: function (picker) {
                    var end = new Date();
                    var start = new Date();
                    start.setTime(start.getTime() - 3600 * 1000 * 24 * 365 * 3);
                    if (end.getHours() >= 15) {
                        end.setTime(end.getTime() + 3600 * 1000 * 24);
                    }
                    picker.$emit('pick', [start, end]);
                }
            }]


        },
        loading: false,
        conditions: [],
        fastArray: [],
        specialString: 'category_ndbg_szsh;category_bndbg_szsh;category_yjdbg_szsh;category_sjdbg_szsh;',
        specialStr: 'category_ndbg_jjgg;category_bndbg_jjgg;category_jdbg_jjgg;',
        specString:'category_jjzm_jjgg',
        fourTitleChange: '',
    },
    filters: {
        //时间
        fomatDate: function (val, type) {
            if (!val) {
                return ''
            }
            return fomatDate(val, type)
        },
        handleDate: function (val) {
            if (!val) {
                return '-';
            }
            return val.split(' ')[0]
        }
    },
    watch: {
        conditions: function () {
            return this.chekedCategory.concat(this.keyWordsArray);
        }
    },
    methods: {
        doHandleMonth: function(month) {
            var m = month;
            if (month.toString().length == 1) {
                m = "0" + month;
            }
            return m;
        },
        getRecentMonth_Date: function(n) {
            var result = '';
            var datenow = new Date();
            var nowMonth = this.doHandleMonth(datenow.getMonth() + 1)
            var nowDate = this.doHandleMonth(datenow.getDate())
            var dateend =
                datenow.getFullYear().toString() +
                '-' +
                nowMonth +
                '-' + nowDate;
            datenow.setMonth(datenow.getMonth() - n);
            var dyear = datenow.getFullYear();
            var dmonth = datenow.getMonth() + 1;
            dmonth = this.doHandleMonth(dmonth)
            var dday = this.doHandleMonth(datenow.getDate()+1)
            var datestart =
                dyear.toString() + '-' + dmonth + '-' + dday;
            result += datestart + ',';
            result += dateend;
            return result.split(',');
        },
        latestAnnounceMount: function (callback) {
            //公告 摘要 调研 定期报告 的下拉框分类 获取
            this.getCategoryJson(callback);
        },
        //查询分类
        getCategoryJson: function (callback) {
            var _this = this;
            $.ajax({
                "url": path + "/data/list-search.json",
                "async": false,
                "type": "get",
                "dataType": "json"
            }).done(function (result) {
                if (result) {
                    _this.relationType = result[plate]["relation"];//调研
                    _this.periodType = result[plate]["period"];//定期报告
                    _this.fulltextAndSummary = result[plate]["category"];
                    if (plate == 'sse') {
                        //沪市没有退市整理器，针对json文件返回值，删除退市整理期
                        _this.category = _this.fulltextAndSummary.filter(function (item) {
                            return item.key != 'category_tszlq_szsh' && item.value != '退市整理期'
                        })
                    } else {
                        _this.category = _this.fulltextAndSummary; //最新公告  和 摘要
                    }
                }
                callback && callback()
            })
        },
        filterHTMLTag: function (msg) {
            if(!msg){
                return ""
            }
            var msg = msg.replace(/<\/?[^>]*>/g, ''); //去除HTML Tag
            msg = msg.replace(/[|]*\n/, '') //去除行尾空格
            msg = msg.replace(/&npsp;/ig, ''); //去掉npsp
            return msg;
        },
        //近期公告请求
        getAnnouncement: function () {
            var _this = this;
            _this.handldeKeyAndCategory();//处理参数查询
            if (_this.tabType == 5 && _this.categoryString == '') { //当为定期报告且分类为空时，默认给分类参数全部
                if(plate=='fund'){
                    _this.categoryString = "";
                }else{
                    _this.categoryString = _this.specialString;
                }
            };
            if(_this.activeIndex == 26 && plate=='fund' && _this.categoryString == ''){
                _this.categoryString = _this.specialStr
            }
            if(_this.activeIndex == 27) {
                _this.categoryString = _this.specString;
            };
            var data = {
                stock: stockCode + ',' + orgId,
                tabName: _this.tabType == 5 ? 'fulltext' : _this.tabType,
                pageSize: _this.pageSize,
                pageNum: _this.pageNum,
                column: plate,
                category: _this.categoryString,
                plate: _this.codelist,
                seDate: !_this.date ? '' : _this.date[0] + '~' + _this.date[1],
                searchkey: _this.keyWordString,
                secid: '',
                sortName: _this.sortName,
                sortType: _this.sortType,
                isHLtitle: true
            };
            _this.newList = [];
            _this.loading = true;
            $.ajax({
                url: path + '/hisAnnouncement/query',
                type: 'post',
                data: data,
                dataType: 'json',
                success: function (res) {
                    _this.loading = false;
                    if (!res || !res.announcements) {
                        _this.newList = [];
                        _this.totalNum = 0;
                        return
                    }
                    res.announcements.forEach(function(item){
                        item.secName = item.secName? _this.filterHTMLTag(item.secName):item.secName
                    })
                    _this.newList = res.announcements;
                    _this.totalNum = res.totalAnnouncement > _this.pageSize * 100 ? _this.pageSize * 100 : res.totalAnnouncement;
                    _this.totalNumReal = res.totalAnnouncement;
                }
            });
        },
        handleCurrentChange: function (val) {
            this.pageNum = val;
            this.getAnnouncement();
        },
        //二级tab切换
        beforeClick: function (newName, oldName) {
            this.oldTab = oldName;
        },
        //tab选择（最新公告 定期报告 调研 摘要）
        handleClick: function (name) {
            var _this = this
            this.tabType = name;
            if (this.tabType == 'relation') {//调研
                this.category = this.relationType;
            } else if (this.tabType == '5'||this.tabType == '26') {//定期报告
                this.category = this.periodType;
            } else {//公告 摘要
                this.category = this.fulltextAndSummary;
            }
            this.reSetVal();
            var hrefUrl = window.location.href
            if(hrefUrl.indexOf('category_gddh_szsh')!=-1){
                this.$nextTick(function () {
                    var monthDate = _this.getRecentMonth_Date(12)
                    _this.date = monthDate
                    _this.$set(_this.chekedCategory, 0, _this.category[8])
                    _this.conditions = _this.chekedCategory.concat(_this.keyWordsArray)
                    _this.pageNum = 1;
                    _this.getAnnouncement();
                })
            }else{
                this.pageNum = 1;
                this.getAnnouncement();
            }
        },
        //分类选择
        handleChecked: function () {
            this.conditions = this.chekedCategory.concat(this.keyWordsArray);
            this.pageNum = 1;
            this.getAnnouncement();
        },
        /*重置变量*/
        reSetVal: function () {
            var flag = false;  //公告 摘要 保留搜索条件，其他类别清除
            for (var i = 0; i < this.category.length; i++) {
                for (var j = 0; j < this.chekedCategory.length; j++) {
                    if (this.chekedCategory[j].key == this.category[i].key && this.chekedCategory[j].value == this.category[i].value) {
                        flag = true;
                        break
                    }
                }
            }
            if (!flag || flag && (this.tabType == '5' || this.oldTab == '5')) {
                this.chekedCategory = [];
                this.conditions = this.chekedCategory.concat(this.keyWordsArray);
            }
            this.conditions = [];
            this.chekedCategory = [];
            this.keyWordsArray = [];
            this.date = '';
            this.pageNum = 1;
            this.sortType = '';
            this.sortName = '';
        },
        //点击查询
        search: function () {
            this.pageNum = 1;
            this.keySearch();
            //this.getAnnouncement();
        },
        //清除
        clear: function () {
            this.conditions = [];
            this.chekedCategory = [];
            this.keyWordsArray = [];
            this.date = '';
            this.pageNum = 1;
            this.getAnnouncement();
        },
        //删除
        handleDelete: function (tag) {
            if (tag.key == 'keyword') {
                var keyArray = [];
                for (var i = 0; i < this.keyWordsArray.length; i++) {
                    if (this.keyWordsArray[i].value != tag.value) {
                        keyArray.push(this.keyWordsArray[i])
                    }
                }
                this.keyWordsArray = keyArray;
            } else {
                var categoryArray = [];
                for (var i = 0; i < this.chekedCategory.length; i++) {
                    if (this.chekedCategory[i].value != tag.value) {
                        categoryArray.push(this.chekedCategory[i])
                    }
                }
                this.chekedCategory = categoryArray;
            }
            this.conditions.splice(this.conditions.indexOf(tag), 1);
            this.pageNum = 1;
            this.getAnnouncement();
        },
        //排序
        sortChange: function (custom) {
            this.sortName = !custom.order ? '' : 'time';
            this.sortType = custom.order == 'ascending' ? 'asc' : custom.order == 'descending' ? 'desc' : '';
            this.pageNum = 1;
            this.getAnnouncement();
        },
        //关键字 操作
        keySearch: function () {
            var keyword = this.keyWords;
            var re = /select|update|delete|exec|count|……|，|\*|——|【|】|[|]|{|}|、|“|”|《|》|。|‘|’|'|"|=|~|!|\+|\(|\)|\\|\/|\?|\$|;|>|<|:|：|\^|&|@|#|%/i;
            if (re.test(keyword)) {
                alert("存在非法字符，请重新输入");
                this.keyWords = '';
                return;
            }
            var obj = {
                key: 'keyword',
                value: this.keyWords
            };
            if (!this.delRepeatArray()) {
                if (this.keyWords.length > 0) {
                    this.keyWordsArray.push(obj);
                    this.conditions.push(obj);
                    this.keyWords = '';
                }
                this.pageNum = 1;
                this.getAnnouncement();
            }
        },
        //选择时间
        chooseTime: function () {
            this.pageNum = 1;
            this.getAnnouncement();
        },
        //关键字是否重复
        delRepeatArray: function () {
            var array = this.keyWordsArray;
            var flag = false;
            for (var i = 0; i < array.length; i++) {
                if (array[i].value == this.keyWords) {
                    flag = true;
                    break;
                }
            }
            return flag
        },
        //处理查询参数
        handldeKeyAndCategory: function () {
            var arr = this.conditions;
            var keyStr = '';
            var categoryStr = '';
            for (var i = 0; i < arr.length; i++) {
                if (arr[i].key == 'keyword') {
                    keyStr += arr[i].value + ';';
                } else {
                    categoryStr += arr[i].key + ';';
                }
            }
            this.keyWordString = keyStr;
            this.categoryString = categoryStr.length <= 1 ? '' : categoryStr;
        },
        //处理分类数据格式
        handleObj: function (item) {
            var arry = [];
            for (var key in item) {
                var obj = {};
                obj = {
                    "key": key,
                    "value": item[key]
                };

                arry.push(obj)
            }
            return arry
        },
        //埋点class
        snowplow: function (adjunctType) {
            if (plate == 'szse'|| plate == 'fund') {
                if (adjunctType == 'DOCX' || adjunctType == 'DOC' || adjunctType == 'PPT' || adjunctType == 'PPTX'
                    || adjunctType == 'JPG' || adjunctType == 'GIF' || adjunctType == 'PNG' ||
                    adjunctType == 'XLSX' || adjunctType == 'XLS' || adjunctType == 'CSV') {
                    return 'doc-snowplow';
                }
                return ''
            }
            return ''
        },
        //图标类型
        checkAjunctType: function (adjunctType) {
            if (adjunctType == "DOC" || adjunctType == "DOCX") {
                return 'iconnotice-DOC1';
            } else if (adjunctType == "PDF") {
                return 'iconnotice-PDF1';
            } else if (adjunctType == "PPT" || adjunctType == "PPTX") {
                return 'iconnotice-PPT1';
            } else if (adjunctType == "XLS" || adjunctType == "XLSX" || adjunctType == "CSV") {
                return 'iconnotice-EXL1';
            } else if (adjunctType == "JPG") {
                return 'iconnotice-JPG1';
            } else if (adjunctType == "GIF") {
                return 'iconnotice-GIF1';
            } else if (adjunctType == "PNG") {
                return 'iconnotice-PNG1';
            } else {
                return '';
            }
        },
        //搜索高亮显示
        replaceWord: function (item) {
            var name = '';
            if (!item.secName) {
                name = ''
            } else {
                name = (item.secName.length>8?item.secName.slice(0,8)+'...':item.secName) + '：'
            }

            if (plate == 'fund') {
                name = (actSecName.length>8?actSecName.slice(0,8)+'...':actSecName) + '：'
            }
            item.announcementTitle = !item.announcementTitle ? '' : item.announcementTitle;
            var str = name + item.announcementTitle;
            /*if(this.keyWordString != ''){
                var arr = this.keyWordString.substring(0,vm.keyWordString.length-1).split(';');
                for(var i=0;i<arr.length;i++){
                    str = str.replace(RegExp(arr[i], "g"),'<span class="higlight">'+ arr[i]  + '</span>' );
                }
            }else{
                str = name + item.announcementTitle;
            }*/
            return str;

        },
        //标题跳转
        jumpUrl: function (item) {
            var url = '';

            if (item.adjunctType == 'PPT' || item.adjunctType == 'PPTX' ||
                item.adjunctType == "XLS" || item.adjunctType == "XLSX" || item.adjunctType == "CSV" ||
                item.adjunctType == "DOC" || item.adjunctType == "DOCX") {
                url = officeUrl + encodeURIComponent(v3_cninfo + '/' + item.adjunctUrl);
            } else {

                if (plateCode == 'fund') {
                    var secCodes = item.secCode ? item.secCode.split(',') : [];
                    url = path + '/disclosure/detail?plate=' + plate + '&orgId=' + item.orgId + '&stockCode=' +
                        secCodes[0] + '&announcementId=' + item.announcementId +
                        '&announcementTime=' + fomatDate(item.announcementTime)
                } else {
                    url = path + '/disclosure/detail?plate=' + plate + '&orgId=' + item.orgId + '&stockCode=' +
                        item.secCode + '&announcementId=' + item.announcementId +
                        '&announcementTime=' + fomatDate(item.announcementTime)
                }

            }
            return url
        },
        //搜索框鼠标悬停获取焦点
        inputMouseOver: function (event) {
            $(event.target)[0].focus();
            $(event.target).addClass('active');
        },
        inputMouseLeav: function (event) {
            $(event.target).removeClass('active');
        },
        keydownChange: function (event) {
            this.keyWords = event.target.value;
        }
    }
}
//股本结构
var equityStructure_mixin = {
    data: {
        headArr: ['变动日期'],
        equityStructureTableData: []
    },
    methods: {
        isNumber0: function (str) {
            if (str == '0') {
                return str;
            } else {
                return str || '--';
            }
        },
        equityStructureMount: function () {
            var _this = this;
            _this.isTimeLoading = true;
            axios({
                url: cninfo_data20 + '/stockholderCapital/getStockStructure',
                method: 'get',
                params: {
                    scode: stockCode
                }
            }).then(function (res) {
                _this.isTimeLoading = false;
                if (res.code != 200 || res.data.resultMsg != "success") {
                    return;
                }
                _this.equityStructureTableData = [];
                _this.headArr = ['变动日期'];
                var arr = ['变动原因'];
                var brr = ['已流通股份'];
                var crr = ['人民币普通股/CDR'];
                var drr = ['境内上市外资股(B股)'];
                var err = ['境外上市外资股(H股)'];
                var frr = ['流通受限股份'];
                var grr = ['总股本'];
                if (res.data.records.length > 0) {
                    res.data.records.forEach(function (item) {
                        _this.headArr.push(item.VARYDATE || '--')
                        arr.push(_this.isNumber0(item.F002V))
                        brr.push(_this.isNumber0(item.F021N))
                        crr.push(_this.isNumber0(item.F022N))
                        drr.push(_this.isNumber0(item.F023N))
                        err.push(_this.isNumber0(item.F024N))
                        frr.push(_this.isNumber0(item.F028N))
                        grr.push(_this.isNumber0(item.F003N))
                    })
                }
                _this.equityStructureTableData = [arr, brr, crr, drr, err, frr, grr]
            }).catch(function () {
                _this.isTimeLoading = false;
            })
        },
    }
}

//股东人数
var shareholders_mixin = {
    data: {
        shareholdersObj: {
            shareholdersTableData: [],
            size: 20,
            total: 0,
            pageshareholdersTableData: [],
            num: 1
        }
    },
    methods: {
        shareholdersMount: function () {
            var _this = this;
            _this.isTimeLoading = true;
            axios({
                url: cninfo_data20 + '/stockholderCapital/getStockholderNum',
                method: 'get',
                params: {
                    scode: stockCode
                }
            }).then(function (res) {
                _this.isTimeLoading = false;
                if (res.code != 200 || res.data.resultMsg != "success") {
                    return;
                }
                if (res.data.records.length > 0) {
                    _this.shareholdersObj.shareholdersTableData = res.data.records;
                    _this.shareholdersObj.total = res.data.records.length;
                    if (res.data.records.length < 20) {
                        _this.shareholdersObj.pageshareholdersTableData = _this.shareholdersObj.shareholdersTableData;
                    } else {
                        _this.shareholdersObj.pageshareholdersTableData = _this.shareholdersObj.shareholdersTableData.slice(0, 20);
                    }
                }
            }).catch(function () {
                _this.isTimeLoading = false;
            })
        },
    }
}

//限售解禁
var saleRestriction_mixin = {
    data: {
        saleRestrictionObj: {
            saleRestrictionTableData: [],
            size: 20,
            total: 0,
            pageSaleRestrictionTableData: [],
            num: 1
        }
    },
    methods: {
        saleRestrictionMount: function () {
            var _this = this;
            _this.isTimeLoading = true;
            axios({
                url: cninfo_data20 + '/stockholderCapital/getLiftBan',
                method: 'get',
                params: {
                    scode: stockCode
                }
            }).then(function (res) {
                _this.isTimeLoading = false;
                if (res.code != 200 || res.data.resultMsg != "success") {
                    return;
                }
                if (res.data.records.length > 0) {
                    _this.saleRestrictionObj.saleRestrictionTableData = res.data.records;
                    _this.saleRestrictionObj.total = res.data.records.length;
                    if (res.data.records.length < 20) {
                        _this.saleRestrictionObj.pageSaleRestrictionTableData = _this.saleRestrictionObj.saleRestrictionTableData;
                    } else {
                        _this.saleRestrictionObj.pageSaleRestrictionTableData = _this.saleRestrictionObj.saleRestrictionTableData.slice(0, 20);
                    }
                }
            }).catch(function () {
                _this.isTimeLoading = false;
            })
        },
        //前端分页处理
        saleRestrictionChange: function (num) {
            this.saleRestrictionObj.pageSaleRestrictionTableData = this.saleRestrictionObj.saleRestrictionTableData.slice(20 * num - 20, 20 * num);
        }
    }
}

//股权质押
var equityPledge_mixin = {
    data: {
        equityPledgeObj: {
            equityPledgeTableData: [],
            size: 20,
            total: 0,
            pageequityPledgeTableData: [],
            num: 1
        }
    },
    methods: {
        equityPledgeMount: function () {
            var _this = this;
            _this.isTimeLoading = true;
            axios({
                url: cninfo_data20 + '/stockholderCapital/getEquityPledge',
                method: 'get',
                params: {
                    scode: stockCode
                }
            }).then(function (res) {
                _this.isTimeLoading = false;
                if (res.code != 200 || res.data.resultMsg != "success") {
                    return;
                }
                if (res.data.records.length > 0) {
                    _this.equityPledgeObj.equityPledgeTableData = res.data.records;
                    _this.equityPledgeObj.total = res.data.records.length;

                    if (res.data.records.length < 20) {
                        _this.equityPledgeObj.pageequityPledgeTableData = _this.equityPledgeObj.equityPledgeTableData;
                    } else {
                        _this.equityPledgeObj.pageequityPledgeTableData = _this.equityPledgeObj.equityPledgeTableData.slice(0, 20);
                    }
                }
            }).catch(function () {
                _this.isTimeLoading = false;
            })
        },
        //前端分页处理
        equityPledgeChange: function (num) {
            this.equityPledgeObj.pageequityPledgeTableData = this.equityPledgeObj.equityPledgeTableData.slice(20 * num - 20, 20 * num);
        }
    }
}

//公开信息
var publicInformation_mixin = {
    data: {
        publicInformationObj: {
            publicInformationTableData: [],
            size: 3,
            total: 0,
            pagepublicInformationTableData: [],
            num: 1
        }
    },
    methods: {
        dateChange: function (str) {
            if (!str) {
                return '';
            }
            var arr = str.split('-');
            return arr[0] + '年' + arr[1] + '月' + arr[2] + '日';
        },
        publicInformationMount: function (page) {
            var _this = this;
            _this.isTimeLoading = true;
            if (!page) {
                page = 1
            }
            axios({
                url: cninfo_data20 + '/tradeInformation/getPublicInfo',
                method: 'get',
                params: {
                    scode: stockCode,
                    page: page,
                    rows: 3
                }
            }).then(function (res) {
                _this.isTimeLoading = false;
                if (res.code != 200 || res.data.resultMsg != "success") {
                    return;
                }
                if (res.data.records.length > 0) {
                    _this.publicInformationObj.pagepublicInformationTableData = res.data.records;
                    _this.publicInformationObj.total = res.data.total;
                }
            }).catch(function () {
                _this.isTimeLoading = false;
            })
        },
        //前端分页处理
        publicInformationChange: function (page) {
            this.publicInformationMount(page)
        }
    }
}
// 高管增减持  Executive increase or decrease
//融资融券
var marginTrading_mixin = {
    data: {
        marginTradingObj: {
            marginTradingTableData: [],
            size: 20,
            total: 0,
            pagemarginTradingTableData: [],
            num: 1
        }
    },
    methods: {
        adddouhaoef: function (item, b) {
            if (item[b.property] == '--') {
                return '--'
            } else {
                return this.addfengefu(item[b.property], 0);
            }
        },
        marginTradingMount: function () {
            var _this = this;
            _this.isTimeLoading = true;
            axios({
                url: cninfo_data20 + '/tradeInformation/getMarginTrading',
                method: 'get',
                params: {
                    scode: stockCode
                }
            }).then(function (res) {
                _this.isTimeLoading = false;
                if (res.code != 200 || res.data.resultMsg != "success") {
                    return;
                }
                if (res.data.records.length > 0) {
                    _this.marginTradingObj.marginTradingTableData = res.data.records;
                    _this.marginTradingObj.total = res.data.records.length;

                    if (res.data.records.length < 20) {
                        _this.marginTradingObj.pagemarginTradingTableData = _this.marginTradingObj.marginTradingTableData;
                    } else {
                        _this.marginTradingObj.pagemarginTradingTableData = _this.marginTradingObj.marginTradingTableData.slice(0, 20);
                    }
                }
            }).catch(function () {
                _this.isTimeLoading = false;
            })
        },
        //前端分页处理
        marginTradingChange: function (num) {
            this.marginTradingObj.pagemarginTradingTableData = this.marginTradingObj.marginTradingTableData.slice(20 * num - 20, 20 * num);
        }
    }
}
//大宗交易
var largeTransactions_mixin = {
    data: {
        largeTransactionsObj: {
            largeTransactionsTableData: [],
            size: 20,
            total: 0,
            pagelargeTransactionsTableData: [],
            num: 1
        }
    },
    methods: {
        largeTransactionsMount: function () {
            var _this = this;
            _this.isTimeLoading = true;
            axios({
                url: cninfo_data20 + '/tradeInformation/getIntsDetail',
                method: 'get',
                params: {
                    scode: stockCode
                }
            }).then(function (res) {
                _this.isTimeLoading = false;
                if (res.code != 200 || res.data.resultMsg != "success") {
                    return;
                }
                if (res.data.records.length > 0) {
                    _this.largeTransactionsObj.largeTransactionsTableData = res.data.records;
                    _this.largeTransactionsObj.total = res.data.records.length;

                    if (res.data.records.length < 20) {
                        _this.largeTransactionsObj.pagelargeTransactionsTableData = _this.largeTransactionsObj.largeTransactionsTableData;
                    } else {
                        _this.largeTransactionsObj.pagelargeTransactionsTableData = _this.largeTransactionsObj.largeTransactionsTableData.slice(0, 20);
                    }
                }
            }).catch(function () {
                _this.isTimeLoading = false;
            })
        },
        //前端分页处理
        largeTransactionsChange: function (num) {
            this.largeTransactionsObj.pagelargeTransactionsTableData = this.largeTransactionsObj.largeTransactionsTableData.slice(20 * num - 20, 20 * num);
        }
    }
}
//股东增减持
var shareholdersId_mixin = {
    data: {
        shareholdersIdObj: {
            shareholdersIdTableData: [],
            size: 20,
            total: 0,
            pageshareholdersIdTableData: [],
            num: 1
        }
    },
    methods: {
        shareholdersIdMount: function () {
            var _this = this;
            _this.isTimeLoading = true;
            axios({
                url: cninfo_data20 + '/tradeInformation/getStockholederIncDecDetail',
                method: 'get',
                params: {
                    scode: stockCode
                }
            }).then(function (res) {
                _this.isTimeLoading = false;
                if (res.code != 200 || res.data.resultMsg != "success") {
                    return;
                }
                if (res.data.records.length > 0) {
                    _this.shareholdersIdObj.shareholdersIdTableData = res.data.records;
                    _this.shareholdersIdObj.total = res.data.records.length;

                    if (res.data.records.length < 20) {
                        _this.shareholdersIdObj.pageshareholdersIdTableData = _this.shareholdersIdObj.shareholdersIdTableData;
                    } else {
                        _this.shareholdersIdObj.pageshareholdersIdTableData = _this.shareholdersIdObj.shareholdersIdTableData.slice(0, 20);
                    }
                }
            }).catch(function () {
                _this.isTimeLoading = false;
            })
        },
        //前端分页处理
        shareholdersIdChange: function (num) {
            this.shareholdersIdObj.pageshareholdersIdTableData = this.shareholdersIdObj.shareholdersIdTableData.slice(20 * num - 20, 20 * num);
        },
        shareholdersFormatter1: function (row) {
            if (row.F004N == 0) {
                return 0
            } else {
                return (row.F001C == 'B' ? '' : '-') + this.addfengefu(row.F004N)
            }
        },
        shareholdersFormatter2: function (row) {
            if (row.F005N == 0) {
                return 0;
            } else {
                return (row.F001C == 'B' ? '' : '-') + row.F005N
            }
        }
    }
}
//高管增减持
var executiveId_mixin = {
    data: {
        executiveIdObj: {
            executiveIdTableData: [],
            size: 20,
            total: 0,
            pageexecutiveIdTableData: [],
            num: 1
        }
    },
    methods: {
        executiveFormatter: function (row, b) {
            var value = row[b.property];
            if (value == 0 || value == '--') {
                return value;
            } else if (String(value).charAt(0) == '-' && String(value).charAt(1) != '-') {
                return '-' + this.addfengefu(String(value).slice(1))
            } else {
                return this.addfengefu(String(value))
            }
        },
        executiveIdMount: function () {
            var _this = this;
            _this.isTimeLoading = true;
            axios({
                url: cninfo_data20 + '/tradeInformation/getExecutivesIncDecDetail',
                method: 'get',
                params: {
                    scode: stockCode
                }
            }).then(function (res) {
                _this.isTimeLoading = false;
                if (res.code != 200 || res.data.resultMsg != "success") {
                    return;
                }
                if (res.data.records.length > 0) {
                    _this.executiveIdObj.executiveIdTableData = res.data.records;
                    _this.executiveIdObj.total = res.data.records.length;
                    if (res.data.records.length < 20) {
                        _this.executiveIdObj.pageexecutiveIdTableData = _this.executiveIdObj.executiveIdTableData;
                    } else {
                        _this.executiveIdObj.pageexecutiveIdTableData = _this.executiveIdObj.executiveIdTableData.slice(0, 20);
                    }
                }
            }).catch(function () {
                _this.isTimeLoading = false;
            })
        },
        //前端分页处理
        executiveIdChange: function (num) {
            this.executiveIdObj.pageexecutiveIdTableData = this.executiveIdObj.executiveIdTableData.slice(20 * num - 20, 20 * num);
        }
    }
}

//十大股东
var topTenShareholders_mixin = {
    data: {
        topTenShareholdersActiveIndex: '',
        datearr1: [],
        arr11: [],
        arr12: [],
        arr13: [],
        arr14: [],
        arr15: [],
        topTenShareholdersTableData: []
    },
    methods: {
        topTenShareholdersMount: function () {
            var _this = this;
            _this.isTimeLoading = true;
            axios({
                url: cninfo_data20 + '/stockholderCapital/getTopTenStockholders',
                method: 'get',
                params: {
                    scode: stockCode
                }
            }).then(function (res) {
                _this.isTimeLoading = false;
                if (res.code != 200 || res.data.resultMsg != "success") {
                    return;
                }
                if (res.data.records.length > 0) {
                    res.data.records.forEach(function (item) {
                        _this.datearr1.push(item.F001D)
                    })
                    _this.datearr1 = _this.removeRepeat(_this.datearr1);
                    _this.arr11 = _this.filterfun1(res.data.records, _this.datearr1, 0);
                    _this.arr12 = _this.filterfun1(res.data.records, _this.datearr1, 1);
                    _this.arr13 = _this.filterfun1(res.data.records, _this.datearr1, 2);
                    _this.arr14 = _this.filterfun1(res.data.records, _this.datearr1, 3);
                    _this.arr15 = _this.filterfun1(res.data.records, _this.datearr1, 4);
                    _this.topTenShareholdersActiveIndex = _this.datearr1[0];
                    _this.topTenShareholdersTableData = JSON.parse(JSON.stringify(_this.arr11));
                }
            }).catch(function () {
                _this.isTimeLoading = false;
            })
        },

        filterfun1: function (array, datearr1, index) {
            var brr = array.filter(function (item) {
                return item.F001D == datearr1[index];
            })
            return brr;
        },
        dateChangeBtn1: function (v) {
            var index = this.datearr1.indexOf(v) + 1;
            this.topTenShareholdersTableData = JSON.parse(JSON.stringify(this['arr1' + index]));
        }
    }
}

//十大流通股东
var topTenTradableShareholders_mixin = {
    data: {
        topTenTradableShareholdersActiveIndex: '',
        datearr2: [],
        arr21: [],
        arr22: [],
        arr23: [],
        arr24: [],
        arr25: [],
        topTenTradableShareholdersTableData: []
    },
    methods: {
        topTenTradableShareholdersMount: function () {
            var _this = this;
            _this.isTimeLoading = true;
            axios({
                url: cninfo_data20 + '/stockholderCapital/getTopTenCirculatingStockholders',
                method: 'get',
                params: {
                    scode: stockCode
                }
            }).then(function (res) {
                _this.isTimeLoading = false;
                if (res.code != 200 || res.data.resultMsg != "success") {
                    return;
                }
                if (res.data.records.length > 0) {
                    res.data.records.forEach(function (item) {
                        _this.datearr2.push(item.F001D)
                    })
                    _this.datearr2 = _this.removeRepeat(_this.datearr2);
                    ;
                    _this.arr21 = _this.filterfun2(res.data.records, _this.datearr2, 0);
                    _this.arr22 = _this.filterfun2(res.data.records, _this.datearr2, 1);
                    _this.arr23 = _this.filterfun2(res.data.records, _this.datearr2, 2);
                    _this.arr24 = _this.filterfun2(res.data.records, _this.datearr2, 3);
                    _this.arr25 = _this.filterfun2(res.data.records, _this.datearr2, 4);
                    _this.topTenTradableShareholdersActiveIndex = _this.datearr2[0];
                    _this.topTenTradableShareholdersTableData = JSON.parse(JSON.stringify(_this.arr21));
                }
            }).catch(function () {
                _this.isTimeLoading = false;
            })
        },
        filterfun2: function (array, datearr2, index) {
            var brr = array.filter(function (item) {
                return item.F001D == datearr2[index];
            })
            return brr;
        },
        dateChangeBtn2: function (v) {
            var index = this.datearr2.indexOf(v) + 1;
            this.topTenTradableShareholdersTableData = JSON.parse(JSON.stringify(this['arr2' + index]));
        }
    }
}

//基金持股
var fundHold_mixin = {
    data: {
        fundHoldObj: {
            fundHoldTableData: [],
            size: 20,
            total: 0,
            pageFundHoldTableData: [],
            num: 1
        }
    },
    methods: {
        adddouhaofd: function (item) {
            if (item.F002N == '--') {
                return '--'
            } else {
                return this.addfengefu(item.F002N, 0);
            }
        },
        fundHoldMount: function () {
            var _this = this;
            _this.isTimeLoading = true;
            axios({
                url: cninfo_data20 + '/stockholderCapital/getFundHoldings',
                method: 'get',
                params: {
                    scode: stockCode
                }
            }).then(function (res) {
                _this.isTimeLoading = false;
                if (res.code != 200 || res.data.resultMsg != "success") {
                    return;
                }
                if (res.data.records.length > 0) {
                    _this.fundHoldObj.fundHoldTableData = res.data.records;
                    _this.fundHoldObj.total = res.data.records.length;

                    if (res.data.records.length < 20) {
                        _this.fundHoldObj.pageFundHoldTableData = _this.fundHoldObj.fundHoldTableData;
                    } else {
                        _this.fundHoldObj.pageFundHoldTableData = _this.fundHoldObj.fundHoldTableData.slice(0, 20);
                    }
                }
            }).catch(function () {
                _this.isTimeLoading = false;
            })
        },
        //前端分页处理
        fundHoldPageChange: function (num) {
            this.fundHoldObj.pageFundHoldTableData = this.fundHoldObj.fundHoldTableData.slice(20 * num - 20, 20 * num);
        }
    }
}

// 公司日历
var companyDate_mixin = {
    data: {
        companyDateData: []
    },
    methods: {
        companyDateMount: function () {
            var _this = this;
            _this.isTimeLoading = true;
            // axios({
            //     url: apiServer + '/service/tradingTips',
            //     method: 'get',
            //     params: {
            //         secCode: stockCode
            //     }
            // }).then(function (res) {
            // _this.isTimeLoading = false;
            // _this.companyDateData = res.hint;
            // }).catch(function () {
            //     _this.isTimeLoading = false;
            // })
            JSONP.getJSON(apiServer + '/service/tradingTips?secCode=' + stockCode, {
                jsonpCallback: ''
            }, function (res) {
                _this.isTimeLoading = false;
                _this.companyDateData = res.hint;
            })
        },
    }
}

//互动问答  ||  公司介绍
var vm = new Vue({
    el: '#main',
    mixins: [executivest_mixin, historicalDividend_mixin, latestAnnouncement_mixin,
        equityStructure_mixin, shareholders_mixin, topTenShareholders_mixin,
        topTenTradableShareholders_mixin, fundHold_mixin, saleRestriction_mixin,
        equityPledge_mixin, publicInformation_mixin, marginTrading_mixin, largeTransactions_mixin,
        shareholdersId_mixin, executiveId_mixin, mainIndicators_mixin, financialStatements_mixin, companyDate_mixin],
    data: {
        disclaimerVisible: false,
        myquestion: cninfo_user_url + '/my_wd',
        sign: '',
        leftTabs: ['公司介绍', '公司高管', '历史分红', '最新公告', '互动问答', '定期报告',
            '调研', '摘要', '实时行情', '历史行情', '股本结构', '股东人数', '十大股东', '十大流通股东',
            '基金持股', '限售解禁', '股权质押', '公开信息', '融资融券', '大宗交易', '股东增减持', '高管增减持', '主要指标', '财务报表',  '公司日历'],
        urlIRMStock: '',
        imgpath: '',
        isTimeLoading: true,
        infoTimeLoading:true,
        mageTimeLoading:true,
        havTimeLoading:true,
        industryLoading:true,
        hisTimeLoading:true,
        isshow: false,
        isshowright: false,
        isClick3567: false,//沪市 没有调研 所以影藏掉
        isClick89: false,
        sid: '',
        text: '',
        stockValue: '',
        stockList: '',
        selectStockList: [],
        questionobj: {
            questionQas: [],
            size: 5,
            num: 1,
            total: 0,
            pagequestionQas: []
        },
        defaultIndex: "0",
        passwordtext: '',
        isClick: false,
        firsrData: null,
        activeIndex: "0",
        mapArray: [
            ["companyProfile"],
            ["companyExecutives"],
            ["historicalDividend"],
            ["latestAnnouncement"],
            ["interactiveQa"],
            ["periodicReports"],
            ["research"],
            ["summary"],
            ["realTimeMarket"],
            ["historicalQuotes"],
            ["equityStructure"],
            ["numberOfShareholders"],
            ["topTenShareholders"],
            ["topTenTradableShareholders"],
            ["fundHoldings"],
            ["saleRestrictionLifted"],
            ["equityPledge"],
            ["publicInformation"],
            ["marginTrading"],
            ["largeTransactions"],
            ["shareholdersIncreaseOrDecrease"],
            ["executiveIncreaseOrDecrease"],
            ["mainIndicators"],
            ["financialStatements"],
            ["peerCompare"],
            ["companyDate"],
            ["compSeven"],
            ["compEight"],
            ["compNine"],
            ["compThirty"],
            ["compThirtyOne"],
            ["compThirtyTwo"],
            ["compThirtyTha"],
            ["compThirtyAcid"],
            ["compThirtyDecrease"]
        ],
        tableData: [],
        tableData1: [],
        tableData2: [],
        tableData3: [],
        tableDataInfo:[],
        tableDataBase:[],
        tableDataAll:{},
        tableDataIndustry:[],
        tableDataHeavy:[],
        AssetData:[],
        tableDataHistory:[],
        showDataHistory: [],
        tableDateGuanLian: [],
        marketData: [],
        fundMsg: "",
        fundData:{},
        headData:{},
        manager:"",
        marketFundData:{},
        marketFundData1:{},
        secType: 'szshe',
        time: '-',
        addStock: false,//是否已经添加股票
        isClickZixuan: false,//是否点击自选按钮
        isClickMyQuestion: false,//是否点击我的问答
        isToPeer: false, //是否点击同业对比
        tishimsg: "自选已添加！",
        overviewData: {},
        otherData: {},
        specalMarketData: {
            huanshou: '',
            shiyinglv: '',
            shijinglv: ''
        },
        extrainfo: {},//用来记录同花顺股票代码，行业，板块代码信息
        isNewStock: false, //是否 是上市新股
        k: null,
        chart: null,
        mofangchecked: [],
        mofangoptions: {
            '定期报告': 'dingqi',
            '业绩报告': 'yeji',
            '公开信息': 'gongkai',
            '分红派息': 'fenhong',
            '融资激励': 'rongzi',
            '高管交易': 'gaoguan',
            '股东交易': 'gudong',
            '大宗交易': 'dazong'
        },
        hangqinResult: {},
        activeMenu: 1,
        divide: false,
        fixLeft: false,
        fixLeftBottom: false,
        pageSizeHis:10,
        pageNumHis:1,
        hisTotal:0,
        hisIndex:5,
        periodGrowthRate:"",
        hisGrowthRate:"",
        comCode:'399300',
        comName:'沪深300',
        market:'012002',
        orgid: '9900003101',
        dropList:[
            {
            value:'000001',
            name:'上证指数',
                market:'012001',
                orgid: 'jysh0000002'
        },{
            value:'399300',
            name:'沪深300',
                market:'012002',
                orgid:'9900003101'
        },{
            value:'399311',
            name:'国证1000',
                market:'012002',
                orgid:'9900001261'
        },{
            value:'000012',
            name:'国债指数',
                market:'012001',
                orgid:'jysh0000002'
        }
        ],
        dropLoading:true,
        hisRateDate:[],
        periodDate:[],
        recordsAll: [],
        actTabName: "szse_stock",
        sendCode: '',
        periodValue: 'day',
        periodArray: [{type:'day',name:'日K'},{type:'week',name:'周K'},{type:'month',name:'月K'},{type:'quarter',name:'季K'},{type:'year',name:'年K'}],
        delisted: false,
        delistedLoading: true
    },
    mounted: function () {
        var _this = this;
        var ele = document.getElementsByClassName('left-nav')[0];
        window.onscroll = function ()  {
            var top = document.documentElement.scrollTop || document.body.scrollTop;
            var height = document.documentElement.scrollHeight || document.body.scrollHeight;
            var eleHeight = ele.offsetHeight;
            _this.divide = top > 210 ? true : false;
            _this.fixLeft =  top > 210 ? true : false;
            //453为左侧导航栏距离顶部高度与距离底部元素高度之和
            if(height - top - eleHeight - 453 > 0) {
                _this.fixLeftBottom = false;
            } else {
                _this.fixLeftBottom = true;
                ele.style.bottom = 363 - (height - top - window.innerHeight) + 'px';
            }
        }
        this.mountMethod()
        this.getStockList()
        if(hq_api_enable !== 'true'){
            if(myBrowser() != 'IE'){
                this.$nextTick(function(){
                    if (window.NSDK && window.GUI) {
                        if (_this.activeIndex == 8 || _this.activeIndex == 9){
                            var mainBody = document.getElementById("mainBody");
                            GUI.init(mainBody);
                        }
                        //GUI初始化
                        if (!NSDK.VUE_CONNECT_SUCCESS) {
                            sdkConnect(_this.query); //SDK连接
                        } else {
                            _this.query()
                        }
                    } else {
                        if (!NSDK.VUE_CONNECT_SUCCESS) {
                            sdkConnect(_this.query); //SDK连接
                        }
                    }
                })
            }
        }

    },
    watch: {
        'activeIndex': function (a, b) {
            var na = Number(a);
            var nb = Number(b);
            if (nb > 7 && nb < 10 && na > 7 && na < 10) {
                this.isClick89 = true;
            } else {
                this.isClick89 = false;
                this.mofangchecked = [];
            }

            if (nb > 2 && nb < 8 && nb != 4 && na > 2 && na < 8 && na != 4) {
                this.isClick3567 = true;
            } else {
                this.isClick3567 = false;
            }

        }
    },
    filters: {
        emptyJudge: function (data) {
            if (!data || data == '-') {
                return '-'
            }
            return data
        },
        //保留小数位
        toFixed2: function (value) {
            if (value === 0 || value === '0' || value == '0.00') {
                return '0.00'
            }
            if (!value || value=='-') {
                return '-';
            }
            var num = parseFloat(value).toFixed(2);
            if (String(num).indexOf('.') > 0) {
                var arr = String(num).split('.');
                num = toThousands(arr[0]) + '.' + arr[1];
            }
            return num;
        },
        //百分比
        toPercent: function (value) {
            if (!value || value=='-') {
                return '-'
            }
            if (value === 0 || value === '0' || value == '0.00') {
                return '0.00%'
            }
            return Number(value).toFixed(2) + "%";
        },
        unitChange: function (value) {
            if (value === 0 || value === '0' || value == '0.00') {
                return '0.00股'
            }
            if (!value || value=='-') {
                return '-'
            }
            var num = '';
            var danwei = '';
            if (Number(value) / Math.pow(10, 8) > 1) {
                num = Number(parseFloat(value / Math.pow(10, 8))).toFixed(2);
                danwei = '亿股'
            } else {
                num = Number(parseFloat(value / Math.pow(10, 4))).toFixed(2);
                danwei = '万股'
            }
            if (String(num).indexOf('.') > 0) {
                var arr = String(num).split('.');
                num = toThousands(arr[0]) + '.' + arr[1];
            }
            return num + danwei;
        },
        toHundredMillon: function (value) {
            if (value === 0 || value === '0' || value == '0.00') {
                return '0.00亿'
            }
            if (!value || value=='-') {
                return '-'
            }
            var num = Number(parseFloat(value / 100000000)).toFixed(2);
            if (String(num).indexOf('.') > 0) {
                var arr = String(num).split('.');
                num = toThousands(arr[0]) + '.' + arr[1];
            }
            return num + '亿';
        }
    },
    beforeDestroy: function(){
        var _this = this
        Bus.$off('TopSearchInput_Full_Event')
        if (hq_api_enable !== 'true' && myBrowser() != 'IE'){
            NSDK.destroyRequestItem(_this.subscribe);
        }
    },
    methods: {
        // this.mapArray[index][0]
        getStockList: function () {
            var _this = this;
            axios({
                url: path + '/data/' + _this.actTabName + '.json',
                method: 'get',
            }).then(function (res) {
                if (res) {
                    _this.stockList = res.stockList;
                }
            }).catch(function (err) {
            })
        },
        querySearch: function (queryString, cb) {
            queryString = queryString == '+' || queryString == '?' || queryString == '？' ? '-' : queryString
            var qstr = ToCDb(queryString.toLocaleLowerCase());
            this.selectStockList = [];
            // 判断是否包含特殊字符
            var reg = /([\*^()]{1})/g;
            qstr = qstr.replace(reg, "\\$1")
            var count = 0;
            for (var i = 0, len = this.stockList.length; i < len; i++) {
                if (count >= 10) {
                    break;
                }
                // console.log('qstr',qstr);
                var reg = new RegExp(qstr, "ig");
                var item = this.stockList[i];
                if (reg.test(item.code) || reg.test(item.pinyin) || reg.test(ToCDb(item.zwjc).toLocaleLowerCase())) {
                    count++;
                    this.selectStockList.push(item);
                }
            }
            if(this.selectStockList.length==0){
                this.selectStockList.push({nameText:'没找到相关内容'})
            }
            cb(this.selectStockList);
        },
        wordInputBlur: function () {
            if (this.selectStockList.length == 1) {
                this.selectStock = this.selectStockList[0];
                this.stockValue = this.selectStock.code;
            } else {
                this.stockValue = '';
                this.selectStock = '';
            }
        },
        handleSelect: function (item) {
            if(!item.code){
                this.stockValue = ''
                return
            }
            this.selectStock = item;
            this.stockValue = item.code;
            var href = ''
            if(item.orgId.indexOf('bj')!=-1&&(this.activeMenu==3 || this.activeIndex == 1 || this.activeIndex == 2)){
                href = this.mapArray[3][0]
            }else if(item.orgId.indexOf('sz')==-1&&this.activeIndex==4){
                href = this.mapArray[3][0]
            }else{
                href = this.mapArray[this.activeIndex][0]
            }
            window.location.href = path + '/disclosure/stock?stockCode=' + item.code + '&orgId=' + item.orgId+'#'+href;
        },
        //输入框 回车事件
        enterQuery: function (event) {
            var _this = this
            if(event.keyCode==13&&_this.selectStockList.length==1){
                _this.handleSelect(_this.selectStockList[0])
            }
        },
        query: function() {
            var _this = this
            var stocklist = { stockCode: stockCode, stockName: _this.overviewData.secName }
            $.ajax({
                url: path + '/singleDisclosure/getStockPlateNew',
                type: 'get',
                data: stocklist,
                success: function (data) {
                    if (data.msg != "fail") {
                        var prefix = data.content.market;
                        if (prefix.indexOf("bj")!=-1) {
                            // 可转债暂无北交所
                        } else {
                            var code = stockCode+'.'+(prefix === "sz" ? "SZ" : "SH");
                            _this.sendCode = code;
                            _this.$nextTick(function() {
                                // 获取行情订阅数据
                                _this.getSubscribeData(code);
                                if (_this.activeIndex == 8 || _this.activeIndex == 9){
                                    _this.setQuintSdk(code)
                                    _this.setTimeSdk(code)
                                    _this.setKLINE(code)
                                }
                            });
                        }
                    }
                },
                error: function (err) {
                }
            });
        },
        // 获取行情订阅数据
        getSubscribeData:function(code) {
            this.subscribe = NSDK.createRequestItem(SDK_REQUEST_QUOTESUBSCRIBE);
            this.subscribe.setDataCallback(this.setSubscribeData);
            this.subscribe.setCodes(code);
            this.subscribe.setFields(
                "Last,Change,PercentChange,Time,Volume,TotalShare,Float,PE_TTM,PB,Amount,TurnoverRate,exchtime,name"
            );
            this.subscribe.request();
        },
        // 写入行情订阅数据
        setSubscribeData:function(res) {
            var _this = this
            var data = res.data;
            var rowArray = data.getRowValues(0);
            var dateTime = data.getCellData(0,4).getRawData()
            var exchTime = data.getCellData(0,12).getRawData()
            var dateTimeAll = ((dateTime>exchTime[0][0]&&dateTime<exchTime[0][1])||(dateTime>exchTime[1][0]&&dateTime<exchTime[1][1])) ? dateTime: (dateTime>exchTime[0][1]&&dateTime<exchTime[1][0])?exchTime[0][1]:exchTime[1][1];
            _this.marketData["10"]= rowArray[1]
            _this.marketData["264648"] = rowArray[2]
            _this.marketData["199112"] = rowArray[3]
            _this.time = !dateTimeAll ? '-' : fomatDate(dateTimeAll);
            _this.marketData["13"] = rowArray[5]
            _this.marketData["TotalShare"] = rowArray[6]
            _this.marketData["Float"] = rowArray[7]
            _this.specalMarketData.shiyinglv = rowArray[8]
            _this.specalMarketData.shijinglv = rowArray[9]
            _this.marketData["19"] = rowArray[10]
            _this.specalMarketData.huanshoulv = rowArray[11]
            _this.marketData["133"] = rowArray[13]
        },
        //分时图
        setTimeSdk:function(code){
            var chart_hangqing = document.getElementById('hangqingDom')
            this.GComponentTime = GUI.createComponent(chart_hangqing,UI_COMPONENT_TREND,UI_SCHEME_TYPE_WHITE)
            this.GComponentTime.setCode(code)
            this.GComponentTime.commit()
        },
        //买卖5五档图
        setQuintSdk:function(code){
            var chart_five = document.getElementById('5dang')
            this.GComponentQuint = GUI.createComponent(chart_five,UI_COMPONENT_ORDERBOOK_FIVE,UI_SCHEME_TYPE_WHITE)
            this.GComponentQuint.setCode(code)
            this.GComponentQuint.commit()
        },
        //k线图
        setKLINE:function(code){
            var chart_kline = document.getElementById('dataMofang')
            var perCal = this.periodValue == 'day' ? UI_KLINE_PERIOD_DAY : this.periodValue == 'week' ? UI_KLINE_PERIOD_WEEK : this.periodValue == 'month' ? UI_KLINE_PERIOD_MONTH : this.periodValue == 'year' ? UI_KLINE_PERIOD_YEAR : UI_KLINE_PERIOD_QUARTER
            this.GComponentKline = GUI.createComponent(chart_kline,UI_COMPONENT_KLINE,UI_SCHEME_TYPE_WHITE)
            this.GComponentKline.setCode(code)
            this.GComponentKline.setPeriod(perCal)
            this.GComponentKline.setDividendType(UI_KLINE_CQMODE_FORWARD)
            this.GComponentKline.setOverlyingCodes("")
            this.GComponentKline.setChartType(UI_KLINE_CHARTTYPE_KLINE)
            this.GComponentKline.commit()
        },
        dataselectChangeBtn:function(item){
            this.periodValue = item
            this.setKLINE(this.sendCode)
        },
        //个股页面业绩预告
        //cninfo_data_url
        getPerformance: function(){
            var self = this
            $.ajax({
                type: 'get',
                url: cninfo_data_url + '/centerSpecial/getPerformanceForecast',
                dataType: 'json',
                data: {
                    scode: stockCode
                },
                success: function (data) {
                    var records = data.records.map(function(item){
                        return item.F004V
                    }).filter(function(i){
                        return i && i.trim()
                    })
                    self.recordsAll = records;
                },
                error: function (e) {
                    if (window.console && console.log) {
                        console.log('e：' + e);
                    }
                }
            })
        },
        //每3位数字用逗号隔开
        addfengefu: function (num, tofix) {
            if (!num) {
                num = '--';
            } else {
                num = Number(num).toFixed(tofix).toString();
                var arry = num.split('.');
                if (arry.length > 1) {
                    num = arry[0].replace(/(\d)(?=(?:\d{3})+$)/g, '$1,') + '.' + arry[1];
                } else {
                    num = arry[0].replace(/(\d)(?=(?:\d{3})+$)/g, '$1,')
                }
            }
            return num;
        },
        //关联证券表格字段处理 其中关联证券包含A、B、H、CDR、可转债五类。
        tableDateFormatter: function (scope) {
            if (scope.prop3 == '关联证券') {
                //a股
                var ASECNAME = this.tableDateGuanLian.basicInformation[0].ASECNAME;
                var ASECCODE = this.tableDateGuanLian.basicInformation[0].ASECCODE;
                var AtrutyStr = (ASECNAME && ASECCODE) ? ('A股：' + ASECCODE + ' ' + ASECNAME + '\xa0\xa0\xa0') : '';
                //b股
                var BSECNAME = this.tableDateGuanLian.basicInformation[0].BSECNAME;
                var BSECCODE = this.tableDateGuanLian.basicInformation[0].BSECCODE;
                var BtrutyStr = (BSECNAME && BSECCODE) ? ('B股：' + BSECCODE + ' ' + BSECNAME + '\xa0\xa0\xa0') : '';
                //h股
                var HSECNAME = this.tableDateGuanLian.basicInformation[0].HSECNAME;
                var HSECCODE = this.tableDateGuanLian.basicInformation[0].HSECCODE;
                var HtrutyStr = (HSECNAME && HSECCODE) ? ('H股：' + HSECCODE + ' ' + HSECNAME + '\xa0\xa0\xa0') : '';
                //可转债
                var F052V = this.tableDateGuanLian.basicInformation[0].F052V;
                var F052VStr = F052V ? ('可转债：' + F052V + '\xa0\xa0\xa0') : '';
                //cdr
                var F053V = this.tableDateGuanLian.basicInformation[0].F053V;
                var F053VStr = F053V ? ('CDR：' + F053V) : '';

                var stockCode1 = stockCode.charAt(0);
                //"66130133 万科转1,66130870 万科转2"
                if (stockCode1 == 2 || stockCode1 == 9) {
                    var ahff = AtrutyStr + HtrutyStr + F052VStr + F053VStr;
                    return ahff ? ahff : '--';
                } else {
                    var bhff = BtrutyStr + HtrutyStr + F052VStr + F053VStr;
                    return bhff ? bhff : '--';
                }
            } else {
                return scope.prop4 ? scope.prop4 : '--';
            }
        },
        //行情涨跌样式
        trendClass: function (value) {
            if (!value) {
                return '';
            }
            value = Number(value);
            if (value > 0) {
                return 'up'
            } else if (value < 0) {
                return 'down'
            } else if (value == 0) {
                return 'shownone'
            }
        },
        initParams: function () {
            //主要指标
            this.mainIndicatorsActiveIndex = '全部';
            this.datearr3 = [];
            this.arrall = [];
            this.arr31 = [];
            this.arr32 = [];
            this.arr33 = [];
            this.arr34 = [];
            this.arrone = [];
            this.arrtwo = [];
            this.arrthree = [];
            this.arrfour = [];
            this.arrfive = [];
            this.mainIndicatorsTableData = [];

            //财务报表
            this.aFinanObj1 = {
                aTypereflect1: {
                    '-12-31': 'aArray1',
                    '-09-30': 'aArray2',
                    '-06-30': 'aArray3',
                    '-03-31': 'aArray4'
                },
                aArray1: [],
                aArray2: [],
                aArray3: [],
                aArray4: [],
                aFinancialStatementsActiveIndex: '全部',
                aDatearr4: [],
                aReflect: {'年报': 'aArray1', '三季报': 'aArray2', '中报': 'aArray3', '一季报': 'aArray4',},
                aFinancialStatementsTableData: [],
            };
            this.bFinanObj1 = {
                bTypereflect1: {
                    '-12-31': 'bArray1',
                    '-09-30': 'bArray2',
                    '-06-30': 'bArray3',
                    '-03-31': 'bArray4'
                },
                bArray1: [],
                bArray2: [],
                bArray3: [],
                bArray4: [],
                bFinancialStatementsActiveIndex: '全部',
                bDatearr4: [],
                bReflect: {'年报': 'bArray1', '三季报': 'bArray2', '中报': 'bArray3', '一季报': 'bArray4'},
                bFinancialStatementsTableData: [],
            };
            this.cFinanObj1 = {
                cTypereflect1: {
                    '-12-31': 'cArray1',
                    '-09-30': 'cArray2',
                    '-06-30': 'cArray3',
                    '-03-31': 'cArray4'
                },
                cArray1: [],
                cArray2: [],
                cArray3: [],
                cArray4: [],
                cFinancialStatementsActiveIndex: '全部',
                cDatearr4: [],
                cReflect: {'年报': 'cArray1', '三季报': 'cArray2', '中报': 'cArray3', '一季报': 'cArray4'},
                cFinancialStatementsTableData: [],
            };

            //公司高管
            this.dialogVisible = '';
            this.executivestTableData = [];
            this.executivestMsg = {
                jobonduty: []
            };
            this.executivestObj = {
                executivestTableData: [],
                size: 20,
                total: 0,
                pageExecutivestData: [],
                num: 1
            };
            //历史分红
            this.historicalDividendTableData = [];
            this.historicalDividendObj = {
                historicalDividendTableData: [],
                size: 20,
                total: 0,
                pageHistoricalDividendData: [],
                num: 1
            }

            //最新公告 || 定期报告 || 调研 || 摘要
            this.pageNum = 1
            this.chekedCategory = [] //选中分类列表
            this.date = ''
            this.loading = false
            //互动问答
            this.questionobj = {
                questionQas: [],
                size: 5,
                num: 1,
                total: 0,
                pagequestionQas: []
            }
            //股本结构
            this.headArr = ['变动日期']
            this.equityStructureTableData = []

            //股东人数
            this.shareholdersObj = {
                shareholdersTableData: [],
                size: 20,
                total: 0,
                pageshareholdersTableData: [],
                num: 1
            }


            //限售解禁
            this.saleRestrictionObj = {
                saleRestrictionTableData: [],
                size: 20,
                total: 0,
                pageSaleRestrictionTableData: [],
                num: 1
            }

            //股权质押
            this.equityPledgeObj = {
                equityPledgeTableData: [],
                size: 20,
                total: 0,
                pageequityPledgeTableData: [],
                num: 1
            }

            //公开信息
            this.publicInformationObj = {
                publicInformationTableData: [],
                size: 3,
                total: 0,
                pagepublicInformationTableData: [],
                num: 1
            }

            //融资融券
            this.marginTradingObj = {
                marginTradingTableData: [],
                size: 20,
                total: 0,
                pagemarginTradingTableData: [],
                num: 1
            }

            //大宗交易
            this.largeTransactionsObj = {
                largeTransactionsTableData: [],
                size: 20,
                total: 0,
                pagelargeTransactionsTableData: [],
                num: 1
            }
            //股东增减持
            this.shareholdersIdObj = {
                shareholdersIdTableData: [],
                size: 20,
                total: 0,
                pageshareholdersIdTableData: [],
                num: 1
            }

            //高管增减持
            this.executiveIdObj = {
                executiveIdTableData: [],
                size: 20,
                total: 0,
                pageexecutiveIdTableData: [],
                num: 1
            }

            //十大股东
            this.topTenShareholdersActiveIndex = ''
            this.datearr1 = []
            this.arr11 = []
            this.arr12 = []
            this.arr13 = []
            this.arr14 = []
            this.arr15 = []
            this.topTenShareholdersTableData = []

            //十大流通股东
            this.topTenTradableShareholdersActiveIndex = ''
            this.datearr2 = []
            this.arr21 = []
            this.arr22 = []
            this.arr23 = []
            this.arr24 = []
            this.arr25 = []
            this.topTenTradableShareholdersTableData = []

            //基金持股
            this.fundHoldObj = {
                fundHoldTableData: [],
                size: 20,
                total: 0,
                pageFundHoldTableData: [],
                num: 1
            }

            // 公司日历
            this.companyDateData = []

            //
        },
        //3 5 6 7 的tab公用的接口   之间切换不需要再调用
        within3567: function (callback) {
            if (!this.isClick3567) {
                this.latestAnnounceMount(callback)
            }
        },
        //初始的activeIndex  和  该表activeIndex都会触发函数findDetail
        choosePage: function (activeIndex) {
            // eventTracker('个股_' + this.leftTabs[activeIndex], 'tab点击');
            var _this = this;
            this.initParams();
            if (activeIndex != 8 && activeIndex != 9 && plate!='fund') {
                $('html,body').animate({scrollTop: '0px'}, 600)
            }
            if(activeIndex == 3 || activeIndex == 26 || activeIndex == 27){
                $('html,body').animate({scrollTop: '0px'}, 600)
            }
            // if(activeIndex == 3 || activeIndex == 26 || activeIndex == 27|| activeIndex == 31 || activeIndex == 32 || activeIndex == 33||activeIndex==34){
            //     this.tableDataIndustry = []
            //     this.tableDataHeavy = []
            //     this.AssetData = []
            // }
            if(activeIndex != 31 && activeIndex != 32 ){
                this.tableDataInfo=[]
                this.tableDataBase = []
            }
            if(activeIndex != 29 && activeIndex != 28 && activeIndex != 30){
                this.tableDataIndustry = []
                this.tableDataHeavy = []
                this.AssetData = []
            }
            if(activeIndex != 33 && activeIndex != 34){
                this.showDataHistory = []
                this.hisTotal = 0
                this.pageNumHis = 1
                this.periodDate = []
                this.hisRateDate = []
                this.hisIndex = 5
                this.comCode = '399300'
                this.comName = '沪深300'
                this.market = '012002'
                this.orgid = '9900003101'
            }
            if (activeIndex == 0) {
                this.axiosCompanyProfile();
            } else if (activeIndex == 1) {
                this.executivestMount();
            } else if (activeIndex == 2) {
                this.historicalDividendMount();
            } else if (activeIndex == 3) {
                $('html,body').animate({scrollTop: '0px'}, 600)
                //最新公告
                this.fourTitleChange = '最新公告';
                this.$nextTick(function () {
                    _this.within3567(_this.handleClick('fulltext'));
                })
            } else if (activeIndex == 4) {
                //互动问答
                // this.interactiveQa();
            } else if (activeIndex == 5) {
                //定期报告
                this.fourTitleChange = '定期报告';
                this.$nextTick(function () {
                    _this.handleClick('5');
                })
                this.within3567();
            } else if (activeIndex == 6) {
                //调研
                this.fourTitleChange = '调研';
                this.$nextTick(function () {
                    _this.handleClick('relation');
                })
                this.within3567();
            } else if (activeIndex == 7) {
                // 摘要
                this.fourTitleChange = '摘要';
                this.$nextTick(function () {
                    _this.handleClick('summary');
                })
                this.within3567();
            } else if (activeIndex == 8 || activeIndex == 9) {

                if(hq_api_enable === 'true'){
                    if (this.isClick89) {//8和9之间的切换则 不需要在画图

                        $('html,body').animate({scrollTop: (activeIndex == 8) ? '0px' : '800px'}, 600)
                        return;
                    }
                    this.getCommonParam(function () {
                        //实时行情
                        _this.chart = new PriceChart('#dataHangqing', _this.extrainfo.name, _this.extrainfo.code, apiServer + '/v5/hq/timeLine', {codelist: _this.extrainfo.thscode});
                        _this.chart.trigger();
                        //只有深市有问答
                        // if (plate == 'szse') {
                        // }

                        //实时行情 右侧信息 一分钟更新一次
                        _this.updatestockprice();

                        //历史行情
                        _this.k = new KChart("#dataMofang", _this.extrainfo.name, _this.extrainfo.code, cninfo_data_url + "/cube/dailyLine");
                        _this.k.on();
                    });
                }else{
                    $('html,body').animate({scrollTop: (activeIndex == 8) ? '0px' : '800px'}, 600)
                    if (this.isClick89) {//8和9之间的切换则 不需要在画图
                        $('html,body').animate({scrollTop: (activeIndex == 8) ? '0px' : '800px'}, 600)
                        return;
                    }

                    this.$nextTick(function(){
                        if(myBrowser() != 'IE'){
                            var mainBody = document.getElementById("mainBody");
                            GUI.init(mainBody);
                            _this.setQuintSdk(_this.sendCode)
                            _this.setTimeSdk(_this.sendCode)
                            _this.setKLINE(_this.sendCode)
                        }
                    })
                }
            } else if (activeIndex == 10) {
                this.equityStructureMount();
            } else if (activeIndex == 11) {
                this.shareholdersMount();
            } else if (activeIndex == 12) {
                this.topTenShareholdersMount();
            } else if (activeIndex == 13) {
                this.topTenTradableShareholdersMount();
            } else if (activeIndex == 14) {
                this.fundHoldMount();
            } else if (activeIndex == 15) {
                this.saleRestrictionMount();
            } else if (activeIndex == 16) {
                this.equityPledgeMount();
            } else if (activeIndex == 17) {
                this.publicInformationMount();
            } else if (activeIndex == 18) {
                this.marginTradingMount();
            } else if (activeIndex == 19) {
                this.largeTransactionsMount();
            } else if (activeIndex == 20) {
                this.shareholdersIdMount();
            } else if (activeIndex == 21) {
                this.executiveIdMount();
            } else if (activeIndex == 22) {
                this.mainIndicatorsMount();
            } else if (activeIndex == 23) {
                this.financialStatementsMount();
            } else if (activeIndex == 25) {
                this.companyDateMount();
            }else if(activeIndex == 26){
                //定期报告
                this.fourTitleChange = '定期报告';
                this.$nextTick(function () {
                    _this.handleClick('5');
                })
                this.within3567();
            }else if(activeIndex == 27){
                //定期报告
                _this.fourTitleChange = '发行公告';
                _this.$nextTick(function () {
                    _this.handleClick('5');
                })
                _this.within3567();
            }else if(activeIndex == 28 || activeIndex == 29 ||activeIndex == 30){
                if(_this.tableDataIndustry.length==0 && _this.tableDataHeavy.length==0 && _this.AssetData.length==0){
                    _this.fundHoldIndustry()
                    _this.fundHoldAsset()
                }
                var height = {
                    '28': 0,
                    '29': 600,
                    '30': 1000
                }
                $('html,body').animate({scrollTop: height[activeIndex]}, 400)
                // window.scrollTo(0, height[activeIndex])
            }else if(activeIndex == 31 || activeIndex == 32){
                $('html,body').animate({scrollTop: (activeIndex == 31) ? '0px' : '1000px'}, 600)
                if(_this.tableDataInfo.length==0&&_this.tableDataBase.length==0){
                    _this.axiosFundOverview();
                    _this.fundManager();
                }
            }else if(activeIndex == 33 || activeIndex == 34){
                if(_this.showDataHistory.length==0 && _this.periodDate.length==0 && _this.hisRateDate.length==0 && _this.hisTotal == 0){
                    _this.fundEquityHistory();
                    _this.fundEquityTrend(_this.hisIndex,_this.comCode,_this.comName,_this.market,_this.orgid)
                }
                $('html,body').animate({scrollTop: (activeIndex == 33) ? '0px' : '800px'}, 400)
            }
        },
        updatestockprice: function () {
            var _this = this;
            this.renderMarket2(this.extrainfo.thscode);
            setTimeout(function () {
                _this.updatestockprice();
            }, 60000);
        },
        // axiosFundprice: function () {
        //     var _this = this;
        //     setTimeout(function () {
        //         _this.axiosFundOverview();
        //     }, 60000);
        // },
        renderMarket2: function (codelist) {
            //开始页面渲染
            var _this = this;
            $.ajax({
                type: 'get',
                url: apiServer + '/v5/hq/dataItem',
                dataType: 'jsonp',
                jsonp: "jsonpCallback",
                data: {
                    codelist: codelist
                },
                success: function (result) {
                    if (!result || result.length<1) {
                        return;
                    }
                    var item = result[0];
                    item['157'] = (item['157'] / 100).toFixed(0);
                    item['153'] = (item['153'] / 100).toFixed(0);
                    item['35'] = (item['35'] / 100).toFixed(0);
                    item['33'] = (item['33'] / 100).toFixed(0);
                    item['31'] = (item['31'] / 100).toFixed(0);
                    item['25'] = (item['25'] / 100).toFixed(0);
                    item['27'] = (item['27'] / 100).toFixed(0);
                    item['29'] = (item['29'] / 100).toFixed(0);
                    item['151'] = (item['151'] / 100).toFixed(0);
                    item['155'] = (item['155'] / 100).toFixed(0);
                    item['14'] = (item['14'] / 100).toFixed(0);
                    item['15'] = (item['15'] / 100).toFixed(0);
                    item['395720'] = (item['395720'] / 100).toFixed(0);
                    item['461256'] = (item['461256'] / 1).toFixed(2) + '%';
                    _this.hangqinResult = item;
                }
            });

        },
        getCommonParam: function (callback) {
            var _this = this;
            $.ajax({
                url: cninfo_data_url + '/common/getSzShStock',
                type: 'post',
                data: {stockCode: stockCode},
                async: false,
                success: function (data) {
                    if (data != null) {
                        _this.extrainfo.thscode = data['stockCodeCh'];
                        _this.extrainfo.tradecode = data['tradeCode'];
                        _this.extrainfo.bkcode = data['plate'] + data['category'];
                        _this.extrainfo.code = data['stockCode'];
                        _this.extrainfo.name = data['stockName'];
                        _this.extrainfo.plate = data['category'];
                        _this.extrainfo.orgid = data['orgId'];
                        if (data['tradeCode'] == null || data['tradeCode'].length <= 0) {
                            _this.isNewStock = true;
                        }
                    }
                    if (callback) {
                        callback()
                    }
                }
            });
        },
        //互动问答提示内容过长，按40字分行
        html4irm: function (c) {
            var len = 40;
            if (c == null || c.length <= 40) {
                return c;
            } else {
                var n = c.length / len;
                var r = c.substring(0, len);
                for (var i = 1; i < n; i++) {
                    r += '<br>' + c.substring(i * len, i * len + len);
                }
                if (c.length > n * len) {
                    r += '<br>' + c.substring(n * len);
                }
                return r;
            }
        },
        //数据魔方切换
        onchangemofang: function (checked, elem) {
            var _this = this;
            var v = this.mofangoptions[elem.target.defaultValue];
            var o = {};
            if (v == 'dingqi') {
                o.index = 2;
                o.title = '财';
                o.url = cninfo_data20 + '/marketTrend/getPeriodicReport';
            } else if (v == 'yeji') {
                o.index = 3;
                o.title = '预';
                o.url = cninfo_data20 + '/marketTrend/getPerformanceReport';
            } else if (v == 'gongkai') {
                //埋点
                o.index = 4;
                o.title = '公';
                o.url = cninfo_data20 + '/marketTrend/getPublicInfoTrend';
            } else if (v == 'fenhong') {
                //埋点
                o.index = 5;
                o.title = '分';
                o.url = cninfo_data20 + '/marketTrend/getDividends';
            } else if (v == 'rongzi') {
                o.index = 6;
                o.title = '融';
                o.url = cninfo_data20 + '/marketTrend/getFinancing';
            } else if (v == 'gaoguan') {
                o.index = 7;
                o.title = '高';
                o.url = cninfo_data20 + '/marketTrend/getExecutiveTrading';
            } else if (v == 'gudong') {
                o.index = 8;
                o.title = '股';
                o.url = cninfo_data20 + '/marketTrend/getStockholderTrading';
            } else if (v == 'dazong') {
                o.index = 9;
                o.title = '大';
                o.url = cninfo_data20 + '/marketTrend/getIntsDetailTrend';
            }
            var series = this.k.kchart.series[o.index];
            if (checked) {
                axios({
                    url: o.url,
                    method: 'get',
                    params: {
                        scode: _this.extrainfo.code
                    }
                }).then(function (res) {
                    if (res.code != 200 || res.data.resultMsg != "success") {
                        return;
                    }
                    var data = res.data.records;
                    if (data != null) {
                        var cwdata = [];
                        for (var i = 0; i < data.length; i++) {
                            //融资融券,业绩预告 内容可能过长做换行处理
                            var t = data[i].F003V;
                            if (o.index == 6 || o.index == 3) {
                                t = _this.html4irm(t);
                            }
                            cwdata.push({
                                x: (new Date(data[i].F002D) * 1 + 8 * 60 * 60 * 1000),
                                title: o.title,
                                text: t
                            });
                        }
                        series.setData(cwdata);

                    }
                })
            } else {
                series.setData([]);
            }

        },
        mountMethod: function () {
            var _this = this;
            _this.mustDo(_this);
        },
        mustDo: function (_this) {
            _this.setDefaultIndex(_this);//初始页面会根据url的hash值得出activeIndex
            if(plate == 'fund'){
                // _this.renderCenter()
                _this.renderFundHead()
                // _this.fundAddStr();
                _this.renderFundTrade();
            }else{
                if(plate == 'bj'){
                    _this.axiosCompanyProfile();
                }
                if(hq_api_enable === 'true'){
                    _this.renderMarket();
                }
                _this.getHeadStripData();
                _this.renderTrade(stockCode, orgId);
                _this.isAddStocks(stockCode, orgId);
            };
        },
        gotomyquestion: function () {
            this.isClickMyQuestion=true;
            this.isClickZixuan = false;
            var loginStatus = JC_USER.getLoginStatus();
            if (!loginStatus) {
                this.gotoLogin();
            }else{
                window.open(cninfo_user_url + '/my_wd')
            }
        },
        goPeerCompare: function() {
            this.isToPeer = true;
            // eventTracker('个股_同业对比', "", '');
            getCommonUserInfo();
            var loginStatus = JC_USER.getLoginStatus();
            if (!loginStatus) {
                this.gotoLogin(1);
            }else{
                window.open(cninfo_user_url + '/peers_compare?scode='+stockCode, '_self')
            }
        },
        //文本域聚焦时的操作
        textfocus: function (callback) {
            // 互动问答 根据现有的用户信息(包含未登录)  是否登录 没有登录则会弹出框
            this.isClickZixuan = false;
            var loginStatus = JC_USER.getLoginStatus();
            if (!loginStatus) {
                this.gotoLogin();
            }
        },
        iptcode: function () {
            var _this = this;
            if (this.passwordtext.length > 0) {
                this.isshow = true;
            } else {
                this.isshow = false;
            }
            $.ajax({
                type: 'post',
                xhrFields: {
                    withCredentials: true
                },
                url: path + "/data/kaptcha",
                data: {
                    j_code: this.passwordtext,
                    secrethide: _this.sid
                },
                dataType: 'text',
                success: function (vData) {
                    var tempPath;
                    if (vData != null && vData == "Y") {
                        _this.isshowright = true;
                    } else {
                        _this.isshowright = false;
                    }
                }
            });
        },
        gotoLogin: function (type) {
	        var loginurl=cninfo_user_url_https + '/login?locale=zh&service='+cninfo_user_url+encodeURIComponent('/api/callback?client_name=CasClient');
	        if(type==1){
	        	window.open(loginurl,"_self");
	        }else{
	        	window.open(loginurl);
	        }
            //$('#loginWrapper').show();
            //$('#login_iframe').attr('src', cninfo_user_url_https + '/login?locale=zh&service='+cninfo_user_url+encodeURIComponent('/api/callback?client_name=CasClient&url='+window.location.origin+'/new/transition'));
            //$('#login_iframe').attr('src', cninfo_user_url_https + '/login?locale=zh&service=' + cninfo_user_url + '/api/callback?client_name%3DCasClient%26url%3Dhttp%3A%2F%2Fwww.cninfo.com.cn%2Fnew%2Ftransition');
            //$('#login_iframe').attr('src', cninfo_user_url_https + '/login?locale=zh&service=' + cninfo_user_url + '/api/callback');
        },
        changePic: function () {
            this.passwordtext = '';
            var _this = this;
            $.ajax({
                url: path + "/Kaptcha2.do?" + Math.floor(Math.random() * 100),
                type: 'GET',
                async: false,
                dataType: 'json',
                success: function (vData) {
                    if (vData != null) {
                        if (vData.img != null && vData.sid != null) {
                            _this.sid = vData.sid;
                            _this.imgpath = "data:image/jpeg;base64," + vData.img;
                        }
                    }
                }
            });
        },
        smquestion: function () {
            var _this = this;
            // eventTracker('巨潮提问', "个股互动问答", '埋点提问按钮');
            this.isClickZixuan = false;
            var loginStatus = JC_USER.getLoginStatus();
            if (!loginStatus) {
                this.gotoLogin();
                return;
            }
            if (!this.isshow) {
                this.alertMessage('请输入验证码');
                return;
            }
            if (this.isshow && !this.isshowright) {
                this.alertMessage('请输入正确验证码');
                return;
            }
            var textarea = this.text;
            var contentWrite = textarea.replace(/ |\n/g, '');
            if (!textarea || !contentWrite) {
                this.alertMessage('请输入您的提问');
                return;
            } else {
                $.ajax({
                    type: 'post',
                    dataType: 'json',
                    url: cninfo_user_url + '/api/companyReplies/jvchaoQuestion',
                    xhrFields: {
                        withCredentials: true
                    },
                    data: {
                        stockCode: stockCode,
                        content: contentWrite,
                        // questionAtr: 'qatr0002',
                        // questionPort: 'b'
                    },
                    success: function (data) {
                        if (data.code == '200' && data.data) {
                            _this.alertMessage('提交成功，详情请到互动易查看');
                        } else {
                            _this.alertMessage(data.msg);
                        }
                        _this.changePic();
                        _this.text = '';
                        _this.isshow = false;
                        _this.isshowright = false;
                    }
                });
            }
        },
        //公司介绍
        axiosCompanyProfile: function () {
            var _this = this;
            _this.isTimeLoading = true;
            axios({
                url: cninfo_data20 + '/companyOverview/getCompanyIntroduction',
                method: 'get',
                params: {
                    scode: stockCode
                }
            }).then(function (res) {
                _this.isTimeLoading = false;
                if (res.code != 200 || res.data.resultMsg != "success") {
                    return;
                }
                if (res.data.records && res.data.records.length > 0 && res.data.records[0] && res.data.records[0].basicInformation) {
                    var obj = res.data.records[0].basicInformation[0] || {}
                    var obj2 = res.data.records[0].listingInformation[0] || {}
                    _this.tableDateGuanLian = res.data.records[0];
                    var gsjc = _this.overviewData.secName
                    var tableData1 = [
                        {
                            prop1: '公司名称',
                            prop2: obj.ORGNAME,
							prop3: '英文名称',
                            prop4: obj.F001V
                        },

                        {
                            prop1: '公司简称',
                            prop2: gsjc==null?obj.ASECNAME:gsjc,
							prop3: '公司代码',
                            prop4: obj2.SECCODE
                        },
                        {
                            prop1: '曾用简称',
                            prop2: obj.F002V,
							prop3: '关联证券',
                            prop4: obj.F052V
                        },

						{
                            prop1: '所属市场',
                            prop2: obj.MARKET,
							prop3: '所属行业',
                            prop4: obj.F032V
                        },
                        {
                            prop1: '成立日期',
                            prop2: obj.F010D,
							prop3: '上市日期',
                            prop4: obj.F006D
                        },
                        {
                            prop1: '法人代表',
                            prop2: obj.F003V,
							prop3: '总经理',
                            prop4: obj.F042V
                        },
                        {
                            prop1: '公司董秘',
                            prop2: obj.F018V,
							prop3: '邮政编码',
                            prop4: obj.F006V
                        }, {
                            prop1: '注册地址',
                            prop2: obj.F004V,
							prop3: '办公地址',
                            prop4: obj.F005V
                        },

                        {
                            prop1: '联系电话',
                            prop2: obj.F013V,
							prop3: '传真',
                            prop4: obj.F014V
                        },
                        {
                            prop1: '官方网址',
                            prop2: obj.F011V,
							prop3: '电子邮箱',
                            prop4: obj.F012V
                        },
                        {
                            prop1: '每股面值(元)',
                            prop2: obj2.F007N,
							prop3: '首发价格(元)',
                            prop4: obj2.F008N
                        },
                        {
                            prop1: '首发募资净额(万元)',
                            prop2: obj2.F028N,
							prop3: '\xa0',
                            prop4: "\xa0"
                        },
                    ];
					var tableData3 = [
                        {
                            prop1: '首发主承销商',
                            prop2: obj2.F047V
                        },
                        {
                            prop1: '入选指数',
                            prop2: obj.F044V
                        },
                        {
                            prop1: '主营业务',
                            prop2: obj.F015V
                        },
                        {
                            prop1: '经营范围',
                            prop2: obj.F016V
                        },
                        {
                            prop1: '机构简介',
                            prop2: obj.F017V
                        },
                    ]
                    _this.tableData1 = tableData1;
                    _this.tableData3 = tableData3;
                }
            }).catch(function () {
                _this.isTimeLoading = false;
            })
        },
        gotoQrDetail: function (href) {
            window.open(href)
        },
        //基金概况
        axiosFundOverview: function () {
            var _this = this;
            // 基本信息
            _this.infoTimeLoading = true;
            axios({
                url: cninfo_data20 + '/fundOverview/baseInfo',
                method: 'get',
                params: {
                    scode: stockCode
                }
            }).then(function (res) {
                _this.infoTimeLoading = false;
                if (res.code != 200 || res.data.resultMsg != "success") {
                    return;
                }
                if (res.data.records && res.data.records.length > 0 && res.data.records[0]) {
                    var obj = res.data.records[0] || {}
                    // var obj2 = res.data.records[0].listingInformation[0] || {}
                    _this.tableDataAll = res.data.records[0];
                    // var gsjc = _this.overviewData.secName;
                    var tableDataInfo = [
                        {
                            prop1: '基金全称',
                            prop2: obj.FUNDNAME,
                            prop3: '基金简称',
                            prop4: obj.SECNAME
                        },

                        {
                            prop1: '基金代码',
                            prop2: obj.SECCODE,
                            prop3: '基金类型',
                            prop4: obj.F011V
                        },
                        {
                            prop1: '发行日期',
                            prop2: obj.F006D,
                            prop3: '基金规模',
                            prop4: obj.fundSize
                        },

                        {
                            prop1: '基金管理人',
                            prop2: obj.F025V,
                            prop3: '基金托管人',
                            prop4: obj.F027V
                        },
                        {
                            prop1: '基金经理人',
                            prop2: obj.manager,
                            prop3: '投资风格',
                            prop4: obj.F013V
                        },
                        {
                            prop1: '管理费率',
                            prop2: obj.F022N,
                            prop3: '托管费率',
                            prop4: obj.F021N
                        },
                        {
                            prop1: '业绩比较基准',
                            prop2: obj.F017V,
                            prop3: '风险收益特征',
                            prop4: obj.F016V
                        },
                    ];
                    _this.tableDataInfo = tableDataInfo;
                }
            }).catch(function () {
                _this.infoTimeLoading = false;
            })
        },
        fundManager:function (){
            var _this = this;
            _this.mageTimeLoading = true;
            // 基金经理
            axios({
                url: cninfo_data20 + '/fundOverview/manager',
                method: 'get',
                params: {
                    scode: stockCode
                }
            }).then(function (res) {
                _this.mageTimeLoading = false;
                if (res.code != 200 || res.data.resultMsg != "success") {
                    return;
                }
                if (res.data.records.length > 0) {
                    _this.tableDataBase = []
                    res.data.records.forEach(function(item){
                        _this.tableDataBase.push([
                            {
                                prop1: '姓名',
                                prop2: item.HUMANNAME
                            },
                            {
                                prop1: '上任日期',
                                prop2: item.F001D
                            },
                            {
                                prop1: '基金经理介绍',
                                prop2: item.F014V
                            },
                        ])
                    })
                    // var obj2 = res.data.records[0] || {}
                    // var tableDataBase = [
                    //     {
                    //         prop1: '姓名',
                    //         prop2: obj2.HUMANNAME
                    //     },
                    //     {
                    //         prop1: '上任日期',
                    //         prop2: obj2.F001D
                    //     },
                    //     {
                    //         prop1: '基金经理介绍',
                    //         prop2: obj2.F014V
                    //     },
                    // ]
                    // _this.tableDataBase = tableDataBase;
                }
            }).catch(function () {
                _this.mageTimeLoading = false;
            })
        },
        // 持仓配置
        fundHoldIndustry : function () {
            var _this = this;
            _this.havTimeLoading = true;
            _this.industryLoading = true;

            axios({
                url: cninfo_data20 + '/fundHold/industry',
                method: 'get',
                params: {
                    scode: stockCode
                }
            }).then(function (res) {
                _this.industryLoading = false
                if (res.code != 200 || res.data.resultMsg != "success") {
                    return;
                }
                if (res.data.records && res.data.records.length > 0) {
                    _this.tableDataIndustry = res.data.records;
                }
            }).catch(function (){
                _this.industryLoading = false
            })

            axios({
                url: cninfo_data20 + '/fundHold/heavyHold',
                method: 'get',
                params: {
                    scode: stockCode
                }
            }).then(function (res) {
                _this.havTimeLoading = false
                if (res.code != 200 || res.data.resultMsg != "success") {
                    return;
                }
                if (res.data.records && res.data.records.length > 0) {
                    _this.tableDataHeavy = res.data.records;
                }
            }).catch(function () {
                _this.havTimeLoading = false
            })
        },
        fundHoldAsset: function(){
            var _this = this;
            axios({
                url: cninfo_data20 + '/fundHold/asset',
                method: 'get',
                params: {
                    scode: stockCode
                }
            }).then(function (res) {
                _this.AssetData = res.data.records
                if (res.data.records && res.data.records.length > 0) {
                    res.data.records.pop()
                    _this.echartAsset(res.data.records,'pie6')
                }
            })
        },
        // 业绩净值
        fundEquityHistory: function () {
            var _this = this;
            _this.hisTimeLoading = true;
            axios({
                url: cninfo_data20 + '/fundEquity/historyEquity',
                method: 'get',
                params: {
                    scode: stockCode,
                }
            }).then(function (res) {
                _this.hisTimeLoading = false;
                if (res.code != 200 || res.data.resultMsg != "success") {
                    return;
                }
                if (res.data.records && res.data.records.length > 0) {
                    _this.showDataHistory = res.data.records;
                    _this.hisTotal = res.data.total;
                    _this.handleGetTabel(_this.showDataHistory);
                }
            }).catch(function () {
                _this.hisTimeLoading = false;
            });
        },
        handleGetTabel:function(temp){
            var _this = this;
            var arr = temp.map(function (item){
                return {
                    ENDDATE: item.ENDDATE,
                    F003N: item.F003N,
                    F012N: item.F012N,
                    F006N: item.F006N
                }
            });
            _this.tableDataHistory = arr.slice(_this.pageNumHis*_this.pageSizeHis-_this.pageSizeHis,_this.pageNumHis*_this.pageSizeHis)
        },
        handleChange:function(val){
            var _this = this;
            _this.pageNumHis = val;
            _this.handleGetTabel(_this.showDataHistory);
        },
        handleCommand: function (command) {
            var _this = this
            if (command.value == _this.comCode && command.name == _this.comName) {
                return;
            }
            _this.comCode = command.value
            _this.comName = command.name
            _this.market = command.market
            _this.orgid = command.orgid
            _this.fundEquityTrend(_this.hisIndex,command.value,command.name,command.market,command.orgid)
        },
        fundEquityTrend: function (index,comCode,comName,market,orgid) {
            var _this = this;
            _this.dropLoading = true
            axios({
                url: cninfo_data20 + '/fundEquity/equityTrend',
                method: 'get',
                params: {
                    scode: stockCode,
                    period: index,
                    indexCode: comCode,
                    market: market,
                    orgid: orgid
                }
            }).then(function (res) {
                if (res.data.records.length > 0) {
                    _this.hisRateDate = res.data.records
                    _this.hisGrowthRate = "本基金"
                    _this.dropLoading = false
                    _this.periodDate = res.data.indexRecords
                    _this.periodGrowthRate = comName +"  "+ res.data.indexRecords[0].rate+"%";
                    _this.echartDailyLine(res.data.records, res.data.indexRecords, "yjzsBox",comName);
                    // _this.axiosDailyLine(res.data.records,index,comCode,comName)
                }
            }).catch(function () {
                    _this.dropLoading = false
            });
        },
        // 业绩走势
        axiosDailyLine: function (arr,perIndex,comCode,comName) {
            var _this = this;
            _this.dropLoading = true
            // var indexCode;
            // if (market == "SSE") {
            //     indexCode = "1A0001";
            //     this.market = "SSE"
            // } else if (market == "SZE") {
            //     this.market = "SZE"
            //     indexCode = "399001";
            // }
            $.ajax({
                type: 'get',
                url: apiServer+'/v5/hq/indexDailyLine',
                dataType: 'jsonp',
                jsonp: 'jsonpCallback',
                data: {
                    indexCode: comCode,
                    period:perIndex,
                    fCode: stockCode
                },
                success: function(res){
                    if (!res) {
                        return;
                    };
                    _this.dropLoading = false
                    _this.periodDate = res.data
                    _this.periodGrowthRate = comName +"  "+ res.data[res.data.length-1][11]+"%";
                    _this.echartDailyLine(arr, res.data, "yjzsBox",comName);
                },
                error: function(e) {
                    _this.dropLoading = false
                    if (window.console && console.log) {
                        console.log('e：' + e);
                    };
                }
            })
        },
        hisChange: function (e, index, fatherClassName) {
            var _this = this
            if (index == _this.hisIndex) {
                return;
            }
            _this.hisIndex = index;
            _this.fundEquityTrend(index,_this.comCode,_this.comName,_this.market,_this.orgid);
            var target = $(e.target);
            $("." + fatherClassName + " .rightTab").removeClass('rightTabActive');
            target.addClass("rightTabActive")
        },
        echartDailyLine: function (arr, brr, id,comName) {
            var _this = this;
            var myChart = echarts.init(document.getElementById(id));
            var mapCrr = [];
            var mapArr = arr.map(function (item, index) {
                if (index == 0) {
                    _this.dateValue = item.ENDDATE;
                }
                mapCrr.push(item.ENDDATE)
                return item.periodGrowthRate
            })
            var mapBrr = mapCrr.map(function (item, index) {
                var obj = brr.find(function(itemBrr,indexBrr){
                    return item == itemBrr.date
                })
                if(obj){
                    return obj.rate
                }else{
                    return 0
                }
            })
            var option = {
                visualMap: [{
                    show: false,
                    type: 'continuous',
                    seriesIndex: 0,
                    min: 0,
                    max: 400
                }],
                dataZoom: [
                    {
                        type: "inside",
                        realtime: true,
                        xAxisIndex: [0],
                        show: true,
                        start: 0,
                        end: 100
                    }],
                legend: {
                    bottom: 0,
                    left: "center",
                    data: [_this.hisGrowthRate, _this.periodGrowthRate],
                    icon: "rect",
                    itemGap: 100,
                    textStyle: {
                        color: "#3f454b"
                    },
                },
                tooltip: {
                    trigger: 'axis',
                    backgroundColor:'#fff',
                    borderRadius:2,
                    padding:6,
                    extraCssText:'box-shadow: 0 0 8px 0 rgba(28, 33, 42, 0.2);',
                    textStyle: {
                        color: "#3f454b",
                    },
                    formatter:function(param){
                        var F003Num = ''
                        var F012Num = ''
                        mapCrr.forEach(function(items,indexs){
                            if(param[0].name==items){
                                F012Num = mapArr[indexs]+'%'
                                F003Num = mapBrr[indexs]+'%';
                            }
                        })
                       var str = '<p style="color: #3f454b;font-size:14px;margin-bottom: 4px;">'+param[0].name+'</p>'+
                                  '<p style="font-size: 12px;">'+'<span style="color: #9098A3;margin-right: 60px;float:left">'+'本基金'+'</span>'+'<span style="float: right;">'+F012Num+'</span>'+'</p>'+'<br />'+
                                  '<p style="font-size: 12px;">'+'<span style="color: #9098A3;margin-right: 60px;float:left">'+comName+'</span>'+'<span style="float:right">'+F003Num+'</span>'+'</p>'
                        return str
                    }
                },
                xAxis: [{
                    type: "category",
                    data: mapCrr.reverse(),
                    axisLabel: {
                        textStyle: {
                            color: "#888888",
                            fontSize: 12
                        }
                    },
                    axisTick: {
                      inside: true,
                      alignWithLabel: true,
                    },
                    axisLine: {
                        lineStyle: {
                            color: "#d9d9d9"
                        },
                        onZero: false
                    },
                    splitLine: {
                        show: false
                    }
                }],
                yAxis: [{
                    axisTick: {
                        show: false
                    },
                    axisLine: {
                        lineStyle: {
                            color: "#d9d9d9"
                        }
                    },
                    axisLabel: {
                        textStyle: {
                            color: "#888888"
                        },
                        formatter:'{value} %'
                    },
                    splitLine: {
                        show: true
                    }
                }, {
                    type: "value",
                    scale: true,
                    axisLine: {
                        show:false,
                        lineStyle: {
                            color: "#d9d9d9"
                        }
                    },
                    axisLabel: {
                        show:false,
                        textStyle: {
                            color: "#888888"
                        },
                    },
                    splitLine: {
                        show: false
                    }
                }, {
                    type: "value",
                    scale: true,
                    axisLine: {
                        lineStyle: {
                            color: "#d9d9d9"
                        }
                    },
                    splitLine: {
                        show: false
                    }
                }],
                series: [
                    {
                        name: _this.hisGrowthRate,
                        type: 'line',
                        smooth: true,
                        yAxisIndex: 0,
                        itemStyle: {
                            normal: {
                                color: "#F03132",
                                borderColor: "#F03132",
                                lineStyle: {
                                    color: "#F03132"
                                }
                            }
                        },
                        data: mapArr.reverse()
                    },
                    {
                        name: _this.periodGrowthRate,
                        type: 'line',
                        itemStyle: {
                            normal: {
                                color: "#3981ea",
                                lineStyle: {
                                    color: "#3981ea"
                                }
                            }
                        },
                        smooth: true,
                        yAxisIndex: 0,
                        data: mapBrr.reverse()
                    }
                ]
            };
            myChart.setOption(option);
        },
        echartAsset: function (arr,id) {
            var _this = this;
            if(arr.length==0){
                return
            }
            var option = {
                tooltip:{
                    trigger:"item",
                    // formatter:
                },
                legend: {
                    top: "20%",
                    left: "68%",
                    orient:'vertical',
                    formatter: function (name) {
                        var lengeIndex = 0;
                        arr.forEach(function (items,i){
                             if(items.name == name){
                                 lengeIndex = i
                             }
                         })
                        return name + ":  " + arr[lengeIndex].value+"%"
                    }
                },
                graphic:[{
                    type:'text',
                    style:{
                        fontSize:14
                    }
                }],
                series: [
                    {
                        name: "访问来源",
                        type: 'pie',
                        tooltip:{
                            trigger:'item',
                            formatter: function (params) {
                                var lengeIndex = 0;
                                arr.forEach(function (items,i){
                                    if(items.name == params.name){
                                        lengeIndex = i
                                    }
                                })
                                return params.name + ":  " + arr ? arr[lengeIndex].value+"%" :''
                            }
                        },
                        radius:['60%','90%'],
                        center:['48%','50%'],
                        avoidLabelOverlap:false,
                        label:{
                            show:false,
                            position: 'center'
                        },
                        emphasis:{
                            label:{
                                show:true,
                                fontSize:'20',
                                fontWeight:'bold'
                            },
                        },
                        labelLine:{
                            show:false
                        },
                        data:arr
                    }
                ]
            };
            var myChart = echarts.init(document.getElementById(id));
            myChart.setOption(option);
        },
        //互动问答
        interactiveQa: function () {
            var _this = this;
            _this.changePic();
            $.ajax({
                url: irmApi + '/ssgs/S' + stockCode + '/latest_replies.js',
                dataType: 'script',
                success: function () {
                    var res = null;
                    //全局变量latest_replies
                    if ("undefined" != typeof latest_replies) {
                        res = latest_replies;
                    }
                    if (res.items[0].qContent.length > 0) {
                        _this.urlIRMStock = res.items[0]['qrListUrl'];
                    }
                    _this.questionobj.questionQas = res.items;
                    _this.questionobj.total = res.items.length;
                    _this.questionobj.pagequestionQas = _this.questionobj.questionQas.slice(0, 5);
                }
            });
        },
        //前端分页处理
        pageChange: function (num) {
            this.questionobj.pagequestionQas = this.questionobj.questionQas.slice(5 * num - 5, 5 * num);
        },
        //点击左边导航
        tabsSelect: function (index) {
            var _this = this;
            if (index == this.activeIndex) {
                return
            }
            this.activeIndex = index;
            this.$nextTick(function () {
                _this.choosePage(_this.activeIndex)
            })
            this.setHash(this.mapArray[index][0])
        },
        //通过其他页面跳转到本页码  hash值不一样  对应的tab页不一样
        setDefaultIndex: function (_this) {
            var hash = this.getHash();
            var params = getUrlParam();
            if (!hash) {
                if (!params.type) {
                    hash = 'latestAnnouncement';
                } else if (params.type && params.type == 'market') {
                    hash = 'realTimeMarket';
                } else if (params.type == 'info') {
                    hash = 'companyProfile';
                }
                this.setHash(hash);
            }
            this.mapArray.forEach(function (item, index) {
                if (item[0] == hash) {
                    _this.choosePage(index);
                    _this.defaultIndex = index;
                    _this.activeIndex = index;
                    return;
                }
            })
            this.setActiveMenu();
        },
        //获取当前活跃菜单
        setActiveMenu: function() {
            if(this.activeIndex == 0 || this.activeIndex == 1 || this.activeIndex == 2) {
                this.activeMenu = 0;
            } else if(this.activeIndex == 3 || this.activeIndex == 4 || this.activeIndex == 5 || this.activeIndex == 6 || this.activeIndex == 7||this.activeIndex==26||this.activeIndex==27){
                this.activeMenu = 1;
            } else if(this.activeIndex == 22 || this.activeIndex == 23 || this.activeIndex == 24) {
                this.activeMenu = 2;
            } else if(this.activeIndex == 8 || this.activeIndex == 9||this.activeIndex==33 || this.activeIndex==34) {
                this.activeMenu = 3;
            } else if(this.activeIndex == 10 || this.activeIndex == 11 || this.activeIndex == 12 || this.activeIndex == 13 || this.activeIndex == 14 || this.activeIndex == 15 || this.activeIndex == 16||this.activeIndex==31 || this.activeIndex==32) {
                this.activeMenu = 4;
            } else if(this.activeIndex == 17 || this.activeIndex == 18 || this.activeIndex == 19 || this.activeIndex == 20 || this.activeIndex == 21 || this.activeIndex == 25) {
                this.activeMenu = 5;
            }
        },
        //获取hash值
        getHash: function (url) {
            return decodeURIComponent(url ? url.substring(url.indexOf('#') + 1) : window.location.hash.substr(1));
        },
        // 设置hash值
        setHash: function (hash) {
            window.location.replace('#' + encodeURIComponent(hash))
        },
        addOrDeleteStock: function () {
            this.isClickZixuan = true;
            //异步请求，等待200ms
            getCommonUserInfo();
	            var loginStatus = JC_USER.getLoginStatus();
	            /*
	            * 每次页面刷新都会请求接口 去判断addStock是否true/false(股票是否已经添加)
	            * 股票没有添加可能是因为没有登录  所以当点击自选时候 会进入第二个条件（弹出登录框）
	            * 如果登录了 且没有添加股票 则进入第三个添加条件
	            * */
	            if (!loginStatus) {
                	this.gotoLogin();
                	return;
                }
	            if (this.addStock) {
	                // eventTracker('用户_删除自选', "个股页面删除", '个股页面点击取消自选');
	                this.delectStock(stockCode, orgId);
	            }  else {
	                // eventTracker('用户_添加自选', "个股页面添加", '个股页面点击添加自选股');
	                this.addStocks(stockCode, orgId);
	            }

        },
        alertMessage: function (message) {
            this.$alert(message, '提示');
        },
        //添加股票
        addStocks: function (stockCode, orgId) {
            var _this = this;
            $.ajax({
                url: cninfo_user_url + '/api/portfolio/addStockToPortfolio',
                type: 'post',
                dataType: "json",
                xhrFields: {
                    withCredentials: true
                },
                data: {
                    portfolioId: '',
                    stockCode: stockCode,
                    organId: orgId
                },
                success: function (data) {
                    if (!data) {
                        return
                    }
                    if (data.code == 200 && data.data) {
                        _this.addStock = true;
                        _this.alertMessage('自选已添加！')
                    } else {
                        _this.addStock = false;
                        if(data.msg){
                            _this.alertMessage(data.msg)
                        }else{
                            _this.alertMessage('股票添加失败！')
                        }
                    }
                }
            })
        },
        //删除分组股票
        delectStock: function (stockCode, orgId) {
            var _this = this;
            $.ajax({
                url: cninfo_user_url + '/api/portfolio/deletePortfolioStock',
                type: 'post',
                dataType: "json",
                xhrFields: {
                    withCredentials: true
                },
                data: {
                    portfolioId: '',
                    stockCode: stockCode,
                    organId: orgId
                },
                success: function (data) {
                    if (!data) {
                        return;
                    }
                    if (data.code == 200 && data.data) {
                        _this.addStock = false;
                        _this.alertMessage('自选已删除！')
                    } else {
                        _this.alertMessage('股票删除失败！')
                    }
                }
            })
        },
        //查询股票是否已经添加
        isAddStocks: function (stockCode, orgId , callback) {
            var stocks = stockCode + ',' + orgId + ';';
            var portfolioId = '';
            var _this = this;
            $.ajax({
                url: cninfo_user_url + '/api/portfolio/getSelectedStatus',
                type: 'get',
                dataType: 'json',
                xhrFields: {
                    withCredentials: true
                },
                data: {
                    portfolioId: '',
                    stockCode: stockCode,
                    organId: orgId
                },
                success: function (data) {
                    if (!data) {
                        return;
                    }
                    if (data.code == 200 && data.data) {
                        _this.addStock = true;
                    } else {
                        _this.addStock = false;
                        if(callback){
                            callback();
                        }
                    }
                }
            })
        },
        renderMarket: function () {
            var self = this;
            var codelist = plate == 'szse' ? 'sz' + stockCode : 'sh' + stockCode;
            //取时间字段
            $.ajax({
                type: 'get',
                url: apiServer + '/v5/hq/timeLine',
                dataType: 'jsonp',
                jsonp: 'jsonpCallback',
                data: {
                    codelist: codelist
                },
                success: function (result) {
                    if (!result) {
                        return;
                    }
                    var time = result.datetime;
                    self.time = !result.datetime ? '' : fomatDate(time - 28800000);
                }
            });
            //头部的数据
            $.ajax({
                type: 'get',
                url: apiServer + '/v5/hq/dataItem',
                dataType: 'jsonp',
                jsonp: "jsonpCallback",
                data: {
                    codelist: codelist
                },
                success: function (result) {
                    if (!result || result.length<1) {
                        return;
                    }
                    var item = result[0];
                    self.marketData = item;
                    self.specalMarketData.huanshoulv = item[1968584];//还手率
                    self.specalMarketData.shiyinglv = item[2034120];//市盈率
                    self.specalMarketData.shijinglv = item[1149395];//市净率
                }
            });
        },
        getHeadStripData: function(){
            var self = this
            axios({
                url: cninfo_data20 + '/companyOverview/getHeadStripData',
                method: 'get',
                params: {
                    scode: stockCode
                }
            }).then(function (res) {
                if (res.code != 200 || res.data.resultMsg != "success") {
                    return;
                }
                if (res.data.records.length > 0) {
                    self.otherData = res.data.records[0];
                }
            });
        },
        renderTrade: function (stockCode, orgId) {
            var self = this;
            var dataList = {
                secCode: stockCode,
                orgId: orgId,
                secType: self.secType
            };
            $.ajax({
                type: 'get',
                url: path + '/newInterface/marketOverview',
                dataType: 'json',
                data: dataList,
                success: function (data) {
                    self.delistedLoading = false;
                    if (!data) {
                        return;
                    }
                    var name = data.secName;
                    var secType = data.secType;
                    self.overviewData = data;
                    self.delisted = data.delisted;
                    //用于巨潮用户
                    if ((secType == '001001' || secType == '001013') && name && orgId && stockCode) {
                        var keyword = stockCode + ',' + orgId + ',' + name;
                        //记录cookie
                        self.markUserCookie(keyword);
                    }
                    //若为退市，hash值非最新公告时默认选中公司公告
                    if(self.delisted && self.getHash() != 'latestAnnouncement'){
                        window.location.hash = '#latestAnnouncement';
                        window.location.reload();
                    }
                    //hash为调研类型，沪北默认选中公司公告
                    if(self.getHash() == 'research' && (plate == 'sse' || plate == 'bj')){
                        window.location.hash = '#latestAnnouncement';
                        window.location.reload();
                    }
                },
                error: function (err) {
                    self.delistedLoading = false;
                }
            })
        },
        renderFundTrade: function () {
            var self = this;
            /*var secType = 'notb';*/
            var dataList = {
                secCode: stockCode,
                orgId: orgId,
                secType: plate
            };

            $.ajax({
                type: 'get',
                url: path + '/newInterface/marketOverview',
                dataType: 'json',
                data: dataList,
                success: function (data) {
                    self.marketFundData = data;
                },
                error: function (e) {
                    if (window.console && console.log) {
                        console.log('e：' + e);
                    }
                }
            })

        },
        fundAddStr: function () {
            var self = this;
            axios({
                url: cninfo_data20 + '/companyOverview/getFundHeadStripData',
                method: 'get',
                params: {
                    scode: stockCode
                }
            }).then(function (res) {
                if (res.code != 200 || res.data.resultMsg != "success") {
                    return;
                }
                if (res.data.records.length > 0) {
                    self.marketFundData1 = res.data.records[0];
                    if(res.data.records[0].manager.indexOf("、")!=-1){
                        if(self.manager = res.data.records[0].manager.split("、").length>2){
                            self.manager = res.data.records[0].manager.split("、").slice(0,2).join("、")+"等"
                        }else{
                            self.manager = res.data.records[0].manager.split("、").join("、")
                        }
                    }else{
                        self.manager = res.data.records[0].manager
                    }
                }
            })
        },
        renderCenter: function(){
            var _this = this
            axios({
                url: cninfo_data20 + '/fundHead/isDataCenter',
                method: 'get',
                params: {
                    scode: stockCode
                }
            }).then(function (res) {
                _this.fundMsg = res.data.records[0].msg;
                if(res.data.records[0].msg=="1"){
                    _this.renderFundHead()
                }else{
                    _this.fundAddStr();
                    _this.renderFundTrade();
                }
            })
        },
        renderFundHead: function(){
            var self = this;
            //基金头部的数据
            // axios({
            //     url: cninfo_data20 + '/fundHead/fundHeadHQData',
            //     method: 'get',
            //     params: {
            //         scode: stockCode
            //     }
            // }).then(function (res) {
            //     if (res.data.records.length > 0) {
            //         self.fundData = res.data.records[0];
            //     }
            // })

            axios({
                url: cninfo_data20 + '/fundHead/fundHeadData',
                method: 'get',
                params: {
                    scode: stockCode
                }
            }).then(function (res) {
                if (res.data.records.length > 0) {
                    self.headData = res.data.records[0];
                    if(res.data.records[0].manager.indexOf("、")!=-1){
                        if(self.manager = res.data.records[0].manager.split("、").length>2){
                            self.manager = res.data.records[0].manager.split("、").slice(0,2).join("、")+"等"
                        }else{
                            self.manager = res.data.records[0].manager.split("、").join("、")
                        }
                    }else{
                        self.manager = res.data.records[0].manager
                    }
                }
            })
        },
        showtongtitle:function(overviewData){
            var szhk = overviewData.szhk;
            var sshk = overviewData.sshk;
            if(szhk && sshk){
                return '深港通标的，沪港通标的'
            }else if(szhk && !sshk){
                return '深港通标的'
            }else if (!szhk && sshk){
                return '沪港通标的'
            }
        },
        //记录cook
        markUserCookie: function (varData) {
            varData = $.trim(varData);
            varData = encodeURI(varData);
            var cookieValue = this.getUserCookie(cookieUserName);
            if (cookieValue) {
                // 去重
                var temp = cookieValue.split('|');
                cookieValue = varData;
                for (var i = 0; i < temp.length; i++) {
                    if (temp[i] == varData) {
                        continue;
                    } else {
                        cookieValue += '|' + temp[i];
                    }
                }
            } else {
                cookieValue = varData;
            }
            var exp = new Date();
            exp.setTime(exp.getTime() + 10 * 24 * 60 * 60 * 1000);	//设置过期时间为10天
            document.cookie = cookieUserName + "=" + cookieValue + ";expires=" + exp.toGMTString() + ";path=/;domain=.cninfo.com.cn";
        },
        //获取cookie
        getUserCookie: function (cookieUserName) {
            var strCookie = document.cookie;
            var arrCookie = strCookie.split("; ");
            for (var i = 0; i < arrCookie.length; i++) {
                var arr = arrCookie[i].split("=");
                if (cookieUserName == arr[0]) {
                    return arr[1];
                }
            }
            return "";
        },
        //数组去重
        removeRepeat: function (arr) {
            var brr = [];
            arr.forEach(function (item) {
                if (brr.indexOf(item) == -1) {
                    brr.push(item)
                }
            })
            return brr;
        },
        emptyFormat: function (arr) {
            if (arr) {
                if (arr.length == 0 || JSON.stringify(arr[0]) == '{}') {
                    return arr;
                }
                return arr.map(function (item1) {
                    var keys = Object.keys(item1);
                    var obj = {};
                    keys.forEach(function (item2) {
                        if (item1[item2] == '0') {
                            obj[item2] = '0';
                        } else {
                            obj[item2] = item1[item2] ? item1[item2] : '--';
                        }
                    })
                    return obj;
                })
            }

        }
    }
});

function myBrowser() {
    var userAgent = navigator.userAgent; //取得浏览器的userAgent字符串
    var isOpera = userAgent.indexOf("Opera") > -1;
    if (isOpera) {
        return "Opera"
    }//判断是否Opera浏览器
    if (userAgent.indexOf("Firefox") > -1) {
        return "FF";
    } //判断是否Firefox浏览器
    if (userAgent.indexOf("Chrome") > -1) {
        return "Chrome";
    }
    if (userAgent.indexOf("Safari") > -1) {
        return "Safari";
    } //判断是否Safari浏览器
    if (userAgent.indexOf("compatible") > -1 && userAgent.indexOf("MSIE") > -1 && !isOpera) {
        return "IE";
    }//判断是否IE浏览器
    if (userAgent.indexOf("rv") > -1) {
        return "IE";
    }
}

function closeModal() {
    $('#loginWrapper').hide();
    getCommonUserInfo(function () {
        var loginStatus = JC_USER.getLoginStatus();
        if (LOGIN_CB_TYPE == 'feedback_open') {
            getCommonUserInfo(function () {
                if(loginStatus) {
                    Feed_Back.openDialog();
                    LOGIN_CB_TYPE = '';
                }
            })
        }
        //页面
        //没有添加股票 且 没有登录 当点击自选时候 弹出登录框 登录成功弹框关闭时 会执行添加股票代码
        vm.isAddStocks(stockCode, orgId,function () {
            if (!vm.addStock && vm.isClickZixuan && loginStatus) {
                vm.addStocks(stockCode, orgId, null);
            }
        });
        //点击了我的问答 且登录了 登录成功后关闭登录框就 直接跳转
        if(vm.isClickMyQuestion && loginStatus){
            window.open(cninfo_user_url + '/my_wd')
        }
        // 点击同业对比且登录了 直接跳转
        if(vm.isToPeer && loginStatus){
            window.open(cninfo_user_url + '/peers_compare?scode='+stockCode, '_self')
        }
    });
}

function PriceChart(id, name, code, url, param) {
    this.arrayData = new Array;
    this.mychart;
    this.url = url;
    this.id = id;
    this.name = name;
    this.code = code;
    this.param = param;
    this.irm_q = [];
    this.irm_qa = [];
    this.callback = function (resp) {
        var me = this;
        if (!resp || resp["line"] == null) {
            return;
        }
        var obj = resp["line"];
        this.pre = resp["PRE"];
        var timestart = obj[0][0];
        me.timestart = timestart; //test
        this.ts = [timestart, timestart + 1000 * 60 * 60 * 2, timestart + 1000 * 60 * 60 * 5.5];
        for (var i = 0; i < 242; i++) {
            //空置点 设null
            if (i < obj.length) {
                me.arrayData[i] = [obj[i][0], obj[i][1]];
                if (i == obj.length - 1) {
                    me.timeForLastRefresh = obj[i][0];
                    me.priceForLastRefresh = obj[i][1];
                    me.iForLastNotNull = i;
                }
            } else {
                if (obj.length > 121) {
                    me.arrayData[i] = [obj[obj.length - 1][0] + 60000 * (i - obj.length + 1), null];
                } else {
                    if (i > 121) {
                        me.arrayData[i] = [obj[obj.length - 1][0] + 60000 * (i - obj.length + 1) + 90 * 60000, null];
                    } else {
                        //午盘不交易90分钟
                        me.arrayData[i] = [obj[obj.length - 1][0] + 60000 * (i - obj.length + 1), null];
                    }

                }

            }
        }
        Highcharts.setOptions({
            global: {useUTC: true},
            lang: {
                months: ['一月', '二月', '三月', '四月', '五月', '六月', '七月', '八月', '九月', '十月', '十一月', '十二月'],
                shortMonths: ['1月', '2月', '3月', '4月', '5月', '6月', '7月', '8月', '9月', '10月', '11月', '12月'],
                weekdays: ['周日', '周一', '周二', '周三', '周四', '周五', '周六']

            }
        });
        // Create the chart
        vm.$nextTick(function () {
            $(me.id).highcharts('StockChart', {
                rangeSelector: {
                    enabled: false
                },
                tooltip: {
                    useHTML: true,
                    shared: true,
                    formatter: function () {
                        var p = '';
                        if (this.point) {
                            p += '<b>' + Highcharts.dateFormat('%A, %b %e, %H:%M', this.x) + '</b></br>';
                            p += this.point.text;
                        } else {
                            p = "<b>" + me.name + Highcharts.dateFormat('&nbsp &nbsp  %H:%M:%S', this.x) + "</b>";
                            if (this.y != null && me.pre > 0) {
                                p += "</br>" + this.y.toFixed(2) + "&nbsp &nbsp" + (100.0 * (this.y - me.pre) / me.pre).toFixed(2) + "%";
                            }
                        }
                        return p;
                    },
                    crosshairs: [true, true]
                },
                //与问答提示 冲突
                xAxis: {
                    showFirstLabel: true,
                    showLastLabel: true,
                    labels: {
                        formatter: function () {
                            var returnTime = Highcharts.dateFormat("%H:%M", this.value);
                            if (returnTime == "11:30") {
                                return "11:30/13:00";
                            }

                            return returnTime;
                        }
                    },
                    tickPositions: me.ts
                },
                navigator: {
                    enabled: false
                },
                scrollbar: {
                    enabled: false
                },
                title: {
                    enabled: false
                },
                credits: {
                    enabled: false
                },
                series: [{
                    name: me.name,
                    id: 'dataseries',
                    data: me.arrayData,
                    type: 'area',
                    threshold: null,
                    tooltip: {
                        valueDecimals: 2
                    },

                    fillColor: {
                        linearGradient: {
                            x1: 0,
                            y1: 0,
                            x2: 0,
                            y2: 1
                        },

                        stops: [
                            [0, Highcharts.getOptions().colors[0]],
                            [1, Highcharts.Color(Highcharts.getOptions().colors[0]).setOpacity(0).get('rgba')]
                        ]

                    }
                }, {
                    type: 'flags',
                    name: '问',
                    data: me.irm_q,
                    shape: 'circlepin',
                    color: '#00bae4',
                    fillColor: '#00bae4',
                    width: 10,
                    style: {
                        color: 'white'
                    },
                    onSeries: 'dataseries'
                }, {
                    type: 'flags',
                    name: '答',
                    data: me.irm_qa,
                    shape: 'circlepin',
                    color: '#fe2325',
                    fillColor: '#fe2325',
                    width: 10,
                    style: {
                        color: 'white'
                    },
                    onSeries: 'dataseries'
                }]
            }, function (chart) {
                me.mychart = chart;
            });
        })
    };
    this.callbackForAddPoint = function (resp) {

        var me = this;

        if (!resp || resp["line"] == null) {
            return;
        }
        var obj = resp["line"];
        var t = obj[obj.length - 1][0];
        var p = obj[obj.length - 1][1];

        if (me.mychart == null || typeof me.mychart == undefined) {
            return;
        }
        //次日行情重新画
        if (me.iForLastNotNull > obj.length) {
            me.iForLastNotNull = 0;
            me.arrayData.length = 0;
            if (me.mychart != null) {
                me.mychart.reflow();
            }
            $.ajax({
                url: me.url,
                type: 'get',
                data: me.param,
                dataType: 'jsonp',
                jsonp: 'jsonpCallback',
                success: function (data) {
                    if (data != null) {
                        me.callback(data);
                    }
                }
            });
            return;
        }

        var series = me.mychart.series;

        if (this.iForLastNotNull < 242) {
            if (me.timeForLastRefresh == t) {
                me.mychart.series[0].removePoint(me.iForLastNotNull, false);
                me.mychart.series[0].addPoint([t, p], true);
            } else {


                for (var i = me.iForLastNotNull + 1; i < obj.length; i++) {
                    this.mychart.series[0].removePoint(i, false);
                    if (i == obj.length - 1) {
                        me.mychart.series[0].addPoint([obj[i][0], obj[i][1]], true);
                    } else {
                        me.mychart.series[0].addPoint([obj[i][0], obj[i][1]], false);
                    }
                    me.iForLastNotNull++;
                }
            }
        }
        me.timeForLastRefresh = t;
        me.priceForLastRefresh = p;
    };


    this.updateDataForAddPoint = function (that) {
        var me = that;

        if (istradingtime()) {
            //按交易时间过滤，非交易时间不去动态更新
            $.ajax({
                url: me.url,
                type: 'get',
                data: me.param,
                dataType: 'jsonp',
                jsonp: 'jsonpCallback',
                success: function (data) {
                    if (data != null) {
                        me.callbackForAddPoint(data);
                    }
                }
            });


        }
        //定时器 60秒刷新一次
        setTimeout(function () {
            me.updateDataForAddPoint(me);
        }, 60 * 1000);
    };
    this.updateirm = function (that) {
        var me = that;
        $.ajax({
            url: irmApi + '/ssgs/S' + me.code + '/latest_questions.js',
            dataType: 'script',
            success: function () {
                var o = null;

                if ("undefined" != typeof latest_questions) {
                    o = latest_questions;
                }
                if (o != null) {
                    var q = [];
                    var qa = [];
                    for (var i = 0; i < o.items.length; i++) {
                        if (o.items[i].qContent.length > 0 && o.items[i].rContent.length > 0) {
                            if (checkirmdate(o.items[i].rCreatedDate)) {
                                var rdate = new Date(Date.parse(o.items[i].rCreatedDate.replace(/-/g, "/")));
                                rdate.setHours(rdate.getHours() + 8);
                                rdate.setSeconds(0);
                                var c = '问: ' + o.items[i].qContent + '<br>';
                                c += '答: ' + o.items[i].rContent;
                                qa.push({
                                    x: rdate.getTime(),
                                    title: '答',
                                    text: vm.html4irm(c)
                                });
                            }

                        } else {
                            if (checkirmdate(o.items[i].qCreatedDate)) {
                                var qdate = new Date(Date.parse(o.items[i].qCreatedDate.replace(/-/g, "/")));
                                qdate.setHours(qdate.getHours() + 8);
                                qdate.setSeconds(0);
                                var c = '问: ' + o.items[i].qContent;
                                q.push({
                                    x: qdate.getTime(),
                                    title: '问',
                                    text: vm.html4irm(c)
                                });
                            }
                        }
                    }
                    if (me.mychart != null) {
                        me.mychart.series[1].setData(q);
                        me.mychart.series[2].setData(qa);
                    }
                    me.irm_q = q;
                    me.irm_qa = qa;
                }
            }
        });

        setTimeout(function () {
            me.updateirm(me);
        }, 60 * 1000);
    }

    this.trigger = function () {
        var me = this;
        $.ajax({
            url: me.url,
            type: 'get',
            data: me.param,
            dataType: 'jsonp',
            jsonp: 'jsonpCallback',
            success: function (data) {
                if (data != null) {
                    me.callback(data);
                }
            }
        });
        me.updateDataForAddPoint(me);
        //只有深市有问答
        if (plate == 'szse') {
            me.updateirm(me);
        }
    };
}

function KChart(id, name, code, url) {
    this.kline = new Array;
    this.url = url;
    this.id = id;
    this.name = name;
    this.code = code;
    this.cw = new Array; //定期报告
    this.yc = new Array;//业绩预告
    this.pj = new Array;//公开信息
    this.fh = new Array;//分红派息
    this.rz = new Array;//融资激励
    this.gg = new Array;//高管交易
    this.hg = new Array;//股东交易
    this.dz = new Array;//大宗交易
    this.callback = function (me, data) {
        var obj2 = data;
        var obj = obj2["line"];
        me.kline = obj;
        // split the data set into ohlc and volume
        var ohlc = [],
            volume = [],
            dataLength = obj.length,

            volume = [],
            // set the allowed units for data grouping
            groupingUnits = [
                [
                    'day', // unit name
                    [1] // allowed multiples
                ]
            ],
            i = 0;
        for (i; i < dataLength; i += 1) {
            ohlc.push([
                obj[i][0] + 8 * 60 * 60 * 1000, // the date
                obj[i][1], // open
                obj[i][3], // high
                obj[i][4], // low
                obj[i][2] // close
            ]);
            volume.push([
                obj[i][0] + 8 * 60 * 60 * 1000, // the date
                obj[i][5] // the volume
            ]);
        }
        //******人为添加最后一个点开始******
        var y_close = null;		//当前的时间
        var myDate = Date.parse(new Date());

        ohlc.push([
            myDate, // the date
            y_close, // open
            y_close, // high
            y_close, // low
            y_close // close
        ]);
        volume.push([
            myDate, // the date
            null // the volume
        ]);
        //******人为添加最后一个点结束******
        //常量本地化
        Highcharts.setOptions({
            global: {
                useUTC: true
            },
            lang: {
                rangeSelectorFrom: "日期:",
                rangeSelectorTo: "至",
                rangeSelectorZoom: "范围",
                loading: '加载中...',

                shortMonths: ['1月', '2月', '3月', '4月', '5月', '6月', '7月', '8月', '9月', '10月', '11月', '12月'],
                weekdays: ['星期日', '星期一', '星期二', '星期三', '星期四', '星期五', '星期六']

            }
        });
        // create the chart
        vm.$nextTick(function () {
            $(me.id).highcharts('StockChart', {
                rangeSelector: {
                    selected: 1,
                    inputDateFormat: '%Y-%m-%d' //设置右上角的日期格式
                },
                credits: {
                    enabled: false
                },
                legend: {
                    enabled: false,
                    align: 'left',
                    verticalAlign: 'top',
                    y: 20,
                    shadow: true
                },

                tooltip: {
                    crosshairs: [true, true],
                    dateTimeLabelFormats: {day: '%Y-%m-%d'}
                },

                plotOptions: {
                    //修改蜡烛颜色
                    candlestick: {
                        //color: '#33AA11',
                        //upColor: '#DD2200',
//					lineColor: '#000fff',
//					upLineColor: '#000fff',
                        maker: {
                            states: {
                                hover: {
                                    enabled: false
                                }
                            }
                        }
                    },
                    line: {
                        color: '#D81F15'
                    },

                    //去掉曲线和蜡烛上的hover事件
                    series: {
                        states: {
                            hover: {
                                enabled: false
                            }
                        },
                        line: {
                            marker: {
                                enabled: false
                            }
                        }
                    },
                    scatter: {
                        maker: {
                            radius: 5
                        }
                    }
                },
                xAxis: {
                    labels: {
                        formatter: function () {
                            var returnTime = Highcharts.dateFormat("%m-%d", this.value);

                            return returnTime;
                        }

                    }
                },
                yAxis: [{
                    labels: {
                        align: 'left',
                        x: 3
                    },
                    title: {
                        text: ''
                    },
                    height: '70%',
                    lineWidth: 1
                }, {
                    labels: {
                        align: 'left',
                        x: 3
                    },
                    title: {
                        text: ''
                    },
                    top: '70%',
                    height: '30%',
                    offset: 0,
                    lineWidth: 1
                }],
                series: [{
                    type: 'candlestick',
                    id: 'kline',
                    name: me.name,
                    data: ohlc,
                    dataGrouping: {
                        units: groupingUnits
                    }

                }, {
                    type: 'column',
                    id: 'column',
                    name: '交易额',
                    data: volume,
                    yAxis: 1,
                    dataGrouping: {
                        units: groupingUnits
                    },
                    color: Highcharts.getOptions().colors[0]
                }, {
                    type: 'flags',
                    name: '定期报告',
                    data: me.cw,
                    shape: 'circlepin',
                    width: 10,
                    style: {
                        color: 'white'
                    },
                    color: '#FE0001',
                    fillColor: '#FE0001',
                    onSeries: 'kline'
                }, {
                    type: 'flags',
                    name: '业绩预告',
                    data: me.yc,
                    shape: 'circlepin',
                    width: 10,
                    color: '#3EA92C',
                    fillColor: '#3EA92C',
                    style: {
                        color: 'white'
                    },
                    onSeries: 'kline'
                }, {
                    type: 'flags',
                    name: '公开信息',
                    data: me.pj,
                    shape: 'circlepin',
                    color: '#f1c232',
                    fillColor: '#f1c232',
                    width: 10,
                    style: {
                        color: 'white'
                    },
                    onSeries: 'kline'
                }, {
                    type: 'flags',
                    name: '分红派息',
                    data: me.fh,
                    shape: 'circlepin',
                    width: 10

                }, {
                    type: 'flags',
                    name: '融资激励',
                    data: me.rz,
                    shape: 'circlepin',
                    width: 10,
                    style: {
                        color: '#D81F15'
                    }
                }, {
                    type: 'flags',
                    name: '高管交易',
                    data: me.gg,
                    shape: 'circlepin',
                    width: 10

                }, {
                    type: 'flags',
                    name: '股东交易',
                    data: me.hg,
                    shape: 'circlepin',
                    width: 10

                }, {
                    type: 'flags',
                    name: '大宗交易',
                    data: me.dz,
                    shape: 'circlepin',
                    width: 10

                }]
            }, function (chart) {
                me.kchart = chart;
            });
        })

    }

    this.on = function () {
        var me = this;
        $.ajax({
            url: me.url,
            type: 'get',
            cache: true,
            data: {stockCode: me.code},
            success: function (data) {
                if (data != null) {
                    me.callback(me, data);
                }
            }
        });
    }
}

function checkirmdate(str) {
    //IE firfox 兼容性
    //var date = new Date(str);
    var date = new Date(Date.parse(str.replace(/-/g, "/")));
    var h = date.getHours();
    var m = date.getMinutes();
    var c1 = h == 9 && m >= 25;
    var c2 = h == 10 || (h == 11 && m <= 30);
    var c3 = h >= 13 && h < 15;
    var c4 = h == 15 && m <= 5;

    if (c1 || c2 || c3 || c4) {
        return true;
    } else {
        return false;
    }
}

//交易时间判断
function istradingtime() {
    var date = new Date();
    var h = date.getHours();
    var m = date.getMinutes();
    var c1 = h == 9 && m >= 25;
    var c2 = h == 10 || (h == 11 && m <= 30);
    var c3 = h >= 13 && h < 15;
    var c4 = h == 15 && m <= 5;

    if (c1 || c2 || c3 || c4) {
        return true;
    } else {
        return false;
    }
}

function toThousands(num) {
    var result = '', counter = 0;
    num = (num || 0).toString();
    var arr = [];
    arr = num.split('.');
    num = arr[0];
    for (var i = num.length - 1; i >= 0; i--) {
        counter++;
        result = num.charAt(i) + result;
        if (!(counter % 3) && i != 0) {
            result = ',' + result;
        }
    }
    if (arr[1]) {
        result = result + '.' + arr[1];
    }
    return result;
}





