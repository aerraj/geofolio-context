#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <algorithm>
#include <cmath>
#include <stdexcept>
#include <vector>
namespace py = pybind11;

// Numerically stable centered sums; y is portfolio return, x hedge return.
py::dict hedge(const std::vector<double>& y, const std::vector<double>& x) {
    if (y.size() != x.size() || y.size() < 3)
        throw std::invalid_argument("need at least three aligned return pairs");
    double mx=0, my=0, sxx=0, syy=0, sxy=0;
    for (size_t i=0; i<x.size(); ++i) {
        if (!std::isfinite(x[i]) || !std::isfinite(y[i]))
            throw std::invalid_argument("returns must be finite");
        const double n=static_cast<double>(i+1), dx=x[i]-mx, dy=y[i]-my;
        mx+=dx/n; my+=dy/n;
        sxx+=dx*(x[i]-mx); syy+=dy*(y[i]-my); sxy+=dx*(y[i]-my);
    }
    if (sxx <= 1e-20) throw std::invalid_argument("hedge return variance is zero");
    const double beta=sxy/sxx;
    py::dict out;
    out["ratio"]=beta;
    out["intercept"]=my-beta*mx;
    out["r_squared"]=syy>1e-20 ? std::clamp(sxy*sxy/(sxx*syy),0.0,1.0) : 0.0;
    out["residual_std"]=std::sqrt(std::max(0.0,(syy-beta*sxy)/(x.size()-2)));
    out["samples"]=x.size();
    return out;
}

double haversine(double lat1,double lon1,double lat2,double lon2) {
    for (double v : {lat1,lon1,lat2,lon2})
        if (!std::isfinite(v)) throw std::invalid_argument("coordinates must be finite");
    if (std::abs(lat1)>90 || std::abs(lat2)>90 || std::abs(lon1)>180 || std::abs(lon2)>180)
        throw std::invalid_argument("coordinates out of range");
    constexpr double rad=3.14159265358979323846/180.0;
    const double a=std::pow(std::sin((lat2-lat1)*rad/2),2)
        +std::cos(lat1*rad)*std::cos(lat2*rad)*std::pow(std::sin((lon2-lon1)*rad/2),2);
    return 6371.0088*2*std::asin(std::sqrt(std::clamp(a,0.0,1.0)));
}
PYBIND11_MODULE(_core,m) {
    m.doc()="GeoFolio C++17 analytics kernels";
    m.def("hedge", &hedge);
    m.def("haversine_km", &haversine);
}
